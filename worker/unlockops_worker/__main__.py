"""큐 작업을 받아 MCP를 연결하고, 저장된 LangGraph를 실행·재개하는 진입점."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from functools import partial
from pathlib import Path
from uuid import uuid4

import aio_pika
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from unlockops.access.graph import build_graph
from unlockops.common.models import Job, Result, ToolFailure
from unlockops.common.settings import settings
from unlockops.common.tools import MCPTools
from .phase2 import QUEUES, parse_delivery, progress_event, run_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("unlockops.worker")


class DeliveryFailure(RuntimeError):
    pass


async def main():
    """큐·체크포인트를 준비하고 분석·실행 작업을 순차 소비하는 워커를 실행한다."""
    if settings.mode not in {"demo", "llm"}: raise RuntimeError("AGENT_MODE must be demo or llm")
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
            key = name
            arguments = {} if name == "dead" else {"x-dead-letter-exchange": "unlockops", "x-dead-letter-routing-key": "dead"}
            queue = await channel.declare_queue("unlockops." + name, durable=True, arguments=arguments)
            await queue.bind(exchange, key)
            queues[name] = queue
        lock = asyncio.Lock()  # This SQLite checkpoint worker is intentionally single-flight.

        async def publish(job, kind, data):
            """결과 형식을 검증해 영속 메시지로 발행하고 브로커 확인 실패를 알린다."""
            if "result" in data:
                data = {**data, "result": Result.model_validate(data["result"]).model_dump(mode="json")}
            body = {"event_id": str(uuid4()), "problem_id": job.problem_id,
                    "job_type": job.job_type, "kind": kind, **data}
            try:
                await exchange.publish(aio_pika.Message(json.dumps(body, ensure_ascii=False).encode(),
                    content_type="application/json", delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                    routing_key="results", mandatory=True)
            except Exception:
                raise DeliveryFailure("Result publication not confirmed") from None

        async def publish_v2(event):
            try:
                await exchange.publish(aio_pika.Message(json.dumps(event, ensure_ascii=False).encode(),
                    content_type="application/json", delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
                    routing_key="results", mandatory=True)
            except Exception:
                raise DeliveryFailure("v2 result publication not confirmed") from None

        async def consume(message, *, queue):
            """작업의 그래프를 실행·재개하고 결과 발행 확인 뒤 원본 메시지를 승인한다."""
            async with lock:
                try: job = parse_delivery(message.body, queue)
                except Exception:
                    await message.reject(requeue=False)
                    return
                if not isinstance(job, Job):
                    try:
                        await publish_v2(progress_event(job))
                        event = await run_job(job, saver)
                        if event is not None:
                            await publish_v2(event)
                        await message.ack()
                    except ValueError:
                        # Reused job ID with a conflicting payload is not a transient broker failure.
                        log.error("job=%s code=INVALID_CHECKPOINT_IDENTITY", job.event_id)
                        if not message.processed:
                            await message.reject(requeue=False)
                    except Exception:
                        log.error("job=%s code=V2_DELIVERY_OR_CHECKPOINT_FAILURE", job.event_id)
                        if not message.processed:
                            try: await message.nack(requeue=True)
                            except Exception: pass
                    return
                try:
                    # 같은 요청 ID로 승인 대기 상태와 실행 진행 위치를 다시 찾는다.
                    config = {"configurable": {"thread_id": job.problem_id}, "recursion_limit": 40}
                    async with MCPTools() as tools:
                        graph = build_graph(tools, saver)
                        snapshot = await graph.aget_state(config)
                        if job.job_type == "ANALYZE":
                            interrupted = any(getattr(task, "interrupts", ()) for task in snapshot.tasks)
                            if snapshot.values.get("result") and (not snapshot.next or interrupted):
                                await publish(job, "ANALYZED", {"result": snapshot.values["result"]})
                                await message.ack()
                                return
                            input_value = None if snapshot.values else {"job": job.model_dump(mode="json"), "events": []}
                        else:
                            if not snapshot.values:
                                raise ToolFailure("CHECKPOINT_MISSING", "No analysis checkpoint exists")
                            if not snapshot.next:
                                result = snapshot.values.get("result")
                                if result and result["status"] in {"DONE", "FAILED"}:
                                    await publish(job, "EXECUTED", {"result": result})
                                    await message.ack()
                                    return
                                raise ToolFailure("INVALID_GRAPH_STATE", "Request is not waiting for approval")
                            from unlockops.common.models import Plan
                            if Plan.model_validate(snapshot.values["plan"]).digest() != job.plan_hash:
                                raise ToolFailure("PLAN_CHANGED", "Execution job differs from saved plan")
                            # 승인 대기이면 resume 값을 주고, 이미 재개했다면 저장된 다음 노드를 잇는다.
                            waiting = any(getattr(task, "interrupts", ()) for task in snapshot.tasks)
                            input_value = Command(resume={"approved": True,"plan_hash": job.plan_hash,
                                "idempotency_key": job.idempotency_key}) if waiting else None
                        async for update in graph.astream(input_value, config, stream_mode="updates"):
                            for node, data in update.items():
                                if node == "__interrupt__": continue
                                latest = data.get("events", [])[-1:] if isinstance(data, dict) else []
                                await publish(job, "PROGRESS", {"node": node, "details": latest})
                        final = await graph.aget_state(config)
                        result = Result.model_validate(final.values["result"]).model_dump(mode="json")
                        await publish(job, "ANALYZED" if job.job_type == "ANALYZE" else "EXECUTED", {"result": result})
                    # Publish confirmation happens before acknowledging the work message.
                    await message.ack()
                except (DeliveryFailure, aio_pika.exceptions.AMQPException, ConnectionError, OSError):
                    # A broker failure is not an application-level diagnosis/execution failure.
                    # Leave the original delivery recoverable, including already completed grants.
                    if not message.processed:
                        try: await message.nack(requeue=True)
                        except Exception: pass  # A closed channel automatically requeues unacked work.
                except Exception as exc:
                    code = exc.code if isinstance(exc, ToolFailure) else "WORKER_ERROR"
                    # Log identifiers/codes only; never credentials, full prompts or provider responses.
                    log.error("problem=%s code=%s", job.problem_id, code)
                    try:
                        await publish(job, "FAILED", {"error_code": code})
                        await message.ack()
                    except Exception:
                        # A result-publication outage must not silently lose the original job.
                        await message.nack(requeue=True)

        for name in ("analysis", "execution", "v2.analysis", "v2.execution"):
            await queues[name].consume(partial(consume, queue=name))
        log.info("Worker ready; mode=%s; v1/v2 access + reclaim; single-flight", settings.mode)
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
