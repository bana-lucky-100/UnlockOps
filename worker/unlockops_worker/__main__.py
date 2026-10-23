"""Run current access and reclaim workflows from durable queue jobs."""
from __future__ import annotations
import asyncio
import json
import logging
import os
from functools import partial
from pathlib import Path
import aio_pika
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from unlockops.common.settings import settings
from .runtime import QUEUES, parse_delivery, progress_event, run_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("unlockops.worker")


async def main():
    if settings.mode not in {"demo", "llm"}:
        raise RuntimeError("AGENT_MODE must be demo or llm")
    Path(settings.checkpoint_path).parent.mkdir(parents=True, exist_ok=True)
    connection = await aio_pika.connect_robust(settings.rabbit_url) if settings.rabbit_url else await aio_pika.connect_robust(
        host=os.getenv("RABBIT_HOST", "localhost"), port=int(os.getenv("RABBIT_PORT", "5672")),
        login=os.getenv("RABBIT_USER", os.getenv("RABBITMQ_USER", "unlockops")),
        password=os.getenv("RABBIT_PASSWORD", os.getenv("RABBITMQ_PASSWORD", "unlockops-local-only")))
    async with connection, AsyncSqliteSaver.from_conn_string(settings.checkpoint_path) as saver:
        channel = await connection.channel(publisher_confirms=True, on_return_raises=True)
        await channel.set_qos(prefetch_count=1, global_=True)
        exchange = await channel.declare_exchange("unlockops", aio_pika.ExchangeType.DIRECT, durable=True)
        queues = {}
        for name in QUEUES:
            arguments = {} if name == "dead" else {"x-dead-letter-exchange": "unlockops", "x-dead-letter-routing-key": "dead"}
            queue = await channel.declare_queue("unlockops." + name, durable=True, arguments=arguments)
            await queue.bind(exchange, name)
            queues[name] = queue
        lock = asyncio.Lock()

        async def publish(event):
            await exchange.publish(aio_pika.Message(json.dumps(event, ensure_ascii=False).encode(),
                content_type="application/json", delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                routing_key="results", mandatory=True)

        async def consume(message, *, queue):
            async with lock:
                try:
                    job = parse_delivery(message.body, queue)
                except (ValueError, TypeError):
                    await message.reject(requeue=False)
                    return
                try:
                    await publish(progress_event(job))
                    event = await run_job(job, saver)
                    if event is not None:
                        await publish(event)
                    # The terminal result is checkpointed and broker-confirmed before acknowledgement.
                    await message.ack()
                except ValueError:
                    log.error("job=%s code=INVALID_CHECKPOINT_IDENTITY", job.event_id)
                    if not message.processed:
                        await message.reject(requeue=False)
                except Exception:
                    log.error("job=%s code=DELIVERY_OR_CHECKPOINT_FAILURE", job.event_id)
                    if not message.processed:
                        try:
                            await message.nack(requeue=True)
                        except Exception:
                            pass  # A closed channel requeues unacknowledged deliveries.

        for name in ("v2.analysis", "v2.execution"):
            await queues[name].consume(partial(consume, queue=name))
        log.info("Worker ready; mode=%s; access + reclaim; single-flight", settings.mode)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
