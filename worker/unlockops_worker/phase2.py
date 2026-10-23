"""v2 queue routing and durable result replay, separate from the v1 interrupt graph."""
from __future__ import annotations

import json
import sqlite3
from contextlib import AsyncExitStack
from uuid import uuid5
from unlockops.common.models import Job, ToolFailure
from unlockops.common.phase2 import AccessJob, ReclaimJob, AccessEvent, ReclaimEvent, AccessView, ReclaimRunView
from unlockops.common.phase2_runtime import failure_event
from unlockops.common.tools import MCPTools
from unlockops.common.settings import settings
from unlockops.access.phase2_graph import build_analysis_graph
from unlockops.access.phase2_execution import build_execution_graph
from unlockops.reclaim.graph import build_graph as build_reclaim_graph


QUEUES = ("analysis", "execution", "v2.analysis", "v2.execution", "results", "dead")


def parse_delivery(body: bytes, queue: str):
    raw = json.loads(body)
    if not isinstance(raw, dict):
        raise ValueError("Job must be an object")
    if queue in {"analysis", "execution"}:
        if "schema_version" in raw or "task_type" in raw:
            raise ValueError("Versioned job cannot enter the legacy queue")
        job = Job.model_validate(raw)
        if job.job_type != ("ANALYZE" if queue == "analysis" else "EXECUTE"):
            raise ValueError("Legacy job/queue mismatch")
        return job
    if queue not in {"v2.analysis", "v2.execution"} or type(raw.get("schema_version")) is not int or raw["schema_version"] != 2:
        raise ValueError("Unsupported queue or schema version")
    if raw.get("task_type") == "ACCESS_REQUEST":
        job = AccessJob.model_validate(raw)
        if job.job_type != ("ANALYZE" if queue == "v2.analysis" else "EXECUTE"):
            raise ValueError("Access job/queue mismatch")
        return job
    if raw.get("task_type") == "RECLAIM_SCAN" and queue == "v2.analysis" and raw.get("job_type") == "RECLAIM_CHECK":
        return ReclaimJob.model_validate(raw)
    raise ValueError("Unsupported v2 task/command")


def checkpoint_config(job):
    work_id = job.run_id if isinstance(job, ReclaimJob) else job.problem_id
    return {"configurable": {"thread_id": f"v2:{job.task_type}:{work_id}:{job.job_type}:{job.event_id}"}, "recursion_limit": 30}


def validate_event(event, job):
    model = ReclaimEvent if isinstance(job, ReclaimJob) else AccessEvent
    parsed = model.model_validate(event)
    if parsed.job_event_id != job.event_id:
        raise ValueError("Checkpoint belongs to another job")
    if isinstance(job, AccessJob) and (parsed.problem_id != job.problem_id or parsed.job_type != job.job_type):
        raise ValueError("Checkpoint access identity differs")
    if isinstance(job, ReclaimJob) and parsed.run_id != job.run_id:
        raise ValueError("Checkpoint reclaim identity differs")
    return parsed.model_dump(mode="json")


def progress_event(job):
    if isinstance(job, ReclaimJob):
        return ReclaimEvent(schema_version=2, event_id=uuid5(job.event_id, "v2-progress"), job_event_id=job.event_id,
            run_id=job.run_id, event_type="PROGRESS", result=ReclaimRunView(schema_version=2, run_id=job.run_id,
            status="DIAGNOSING", message="회수 점검을 시작합니다.")).model_dump(mode="json")
    return AccessEvent(schema_version=2, event_id=uuid5(job.event_id, "v2-progress"), job_event_id=job.event_id,
        problem_id=job.problem_id, job_type=job.job_type, event_type="PROGRESS",
        result=AccessView(schema_version=2, problem_id=job.problem_id, status="DIAGNOSING", message="작업을 시작합니다.")).model_dump(mode="json")


class LazyMCP:
    def __init__(self, stack):
        self.stack, self.tools = stack, None

    async def call(self, name, arguments):
        if self.tools is None:
            try:
                self.tools = await self.stack.enter_async_context(MCPTools())
            except Exception:
                raise ToolFailure("MCP_UNAVAILABLE", "MCP connection could not be established", True) from None
        return await self.tools.call(name, arguments)


async def run_job(job, saver, tools=None):
    """Persist terminal payload before publication; redelivery reuses it without tool calls."""
    async with AsyncExitStack() as stack:
        selected_tools = tools if tools is not None else LazyMCP(stack)
        builder = build_reclaim_graph if isinstance(job, ReclaimJob) else build_analysis_graph if job.job_type == "ANALYZE" else build_execution_graph
        graph = builder(selected_tools, job, saver)
        config = checkpoint_config(job)
        snapshot = await graph.aget_state(config)
        serialized = job.model_dump(mode="json")
        if snapshot.values and snapshot.values.get("job") != serialized:
            raise ValueError("A job identity was reused for a different payload")
        if "result_event" in snapshot.values:
            return validate_event(snapshot.values["result_event"], job) if snapshot.values["result_event"] else None
        value = None if snapshot.values else {"job": serialized, "events": []}
        try:
            await graph.ainvoke(value, config)
        except (OSError, ConnectionError, sqlite3.Error):
            # Checkpoint storage failures must be redelivered, not converted into a durable business failure.
            raise
        except Exception:
            # Do not log provider responses or request contents. Keep unexpected failure replay stable too.
            event = failure_event(job, "WORKER_ERROR")
            await graph.aupdate_state(config, {"result_event": event})
        final = await graph.aget_state(config)
        if "result_event" not in final.values:
            raise RuntimeError("Graph did not produce a durable terminal result")
        event = final.values["result_event"]
        if not event:
            return None
        event = validate_event(event, job)
        if len(json.dumps(event, ensure_ascii=False).encode()) > settings.phase2_max_result_bytes:
            event = failure_event(job, "SCAN_LIMIT" if isinstance(job, ReclaimJob) else "WORKER_ERROR")
            await graph.aupdate_state(config, {"result_event": event})
        return event
