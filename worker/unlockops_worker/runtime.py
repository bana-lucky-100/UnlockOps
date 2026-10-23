"""Workflow routing and durable replay for access analysis, execution and reclaim."""
from __future__ import annotations

import json
import sqlite3
from contextlib import AsyncExitStack
from uuid import uuid5
from unlockops.common.models import ToolFailure
from unlockops.common.workflow_contracts import AccessJob, ReclaimJob, AccessEvent, ReclaimEvent, AccessView, ReclaimRunView
from unlockops.common.runtime import failure_event
from unlockops.common.tools import MCPTools
from unlockops.common.settings import settings
from unlockops.access.graph import build_analysis_graph
from unlockops.access.execution import build_execution_graph
from unlockops.reclaim.graph import build_graph as build_reclaim_graph
from unlockops.reclaim.reporting import build_failure_event, report_from_event


QUEUES = ("v2.analysis", "v2.execution", "results", "dead")


def parse_delivery(body: bytes, queue: str):
    raw = json.loads(body)
    if not isinstance(raw, dict):
        raise ValueError("Job must be an object")
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

    async def open(self):
        """Enter MCP cancel scopes in the same Worker task that will close them."""
        if self.tools is None:
            try:
                self.tools = await self.stack.enter_async_context(MCPTools())
            except Exception:
                raise ToolFailure("MCP_UNAVAILABLE", "MCP connection could not be established", True) from None

    async def call(self, name, arguments):
        await self.open()
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
            # Graph nodes run in child tasks. MCP/AnyIO scopes must be opened
            # here, not lazily inside a node and closed in this parent task.
            # Completed checkpoint replay above still needs no MCP connection.
            if isinstance(selected_tools, LazyMCP):
                await selected_tools.open()
            await graph.ainvoke(value, config)
        except (OSError, ConnectionError, sqlite3.Error):
            # Checkpoint storage failures must be redelivered, not converted into a durable business failure.
            raise
        except Exception:
            # Do not log provider responses or request contents. Keep unexpected failure replay stable too.
            if isinstance(job, ReclaimJob):
                latest = await graph.aget_state(config)
                event = build_failure_event(job, latest.values, "WORKER_ERROR", max_bytes=settings.max_result_bytes)
                await graph.aupdate_state(config, {"result_event": event, "report_payload": report_from_event(event)})
            else:
                event = failure_event(job, "WORKER_ERROR")
                await graph.aupdate_state(config, {"result_event": event})
        final = await graph.aget_state(config)
        if "result_event" not in final.values:
            raise RuntimeError("Graph did not produce a durable terminal result")
        event = final.values["result_event"]
        if not event:
            return None
        event = validate_event(event, job)
        if len(json.dumps(event, ensure_ascii=False).encode()) > settings.max_result_bytes:
            if isinstance(job, ReclaimJob):
                event = build_failure_event(job, final.values, "SCAN_LIMIT", max_bytes=settings.max_result_bytes)
                await graph.aupdate_state(config, {"result_event": event, "report_payload": report_from_event(event)})
            else:
                event = failure_event(job, "WORKER_ERROR")
                await graph.aupdate_state(config, {"result_event": event})
        return event


async def read_reclaim_report(job: ReclaimJob, saver, *, display_facts=None):
    """Read a completed Agent report without rescanning, model calls or writes.

    A future server adapter can use this S-04 contract. It does not replace the
    currently deployed strict ReclaimEvent/result/targets queue envelope.
    """
    if not isinstance(job, ReclaimJob):
        raise ValueError("A reclaim job is required")
    graph = build_reclaim_graph(None, job, saver)
    snapshot = await graph.aget_state(checkpoint_config(job))
    if not snapshot.values:
        return None
    if snapshot.values.get("job") != job.model_dump(mode="json"):
        raise ValueError("Checkpoint belongs to another reclaim job")
    event = snapshot.values.get("result_event")
    if not event:
        return None
    return report_from_event(validate_event(event, job), display_facts=display_facts)


async def run_reclaim_report(job: ReclaimJob, saver, tools=None, *, display_facts=None):
    """Run or replay the Agent and return the agreed candidates/needs_review data."""
    if not isinstance(job, ReclaimJob):
        raise ValueError("A reclaim job is required")
    await run_job(job, saver, tools)
    return await read_reclaim_report(job, saver, display_facts=display_facts)
