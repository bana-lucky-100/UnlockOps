"""MCP opening retries stay local to the owning Worker task and preserve checkpoints."""
import asyncio
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import replace
from types import SimpleNamespace

import anyio
import pytest
from langgraph.checkpoint.memory import InMemorySaver

from unlockops.common.models import ToolFailure
from unlockops_worker import runtime as worker
from test_reclaim_agent_design import SnapshotTools, needs_review


def record_backoff(monkeypatch, attempts):
    delays = []

    async def sleep(delay):
        delays.append(delay)

    monkeypatch.setattr(worker, "settings", replace(worker.settings, max_execution_attempts=attempts))
    # Patch only this module, not asyncio.sleep used by LangGraph/AnyIO.
    monkeypatch.setattr(worker, "asyncio", SimpleNamespace(sleep=sleep))
    return delays


@pytest.mark.parametrize("attempts", [1, 3, 4])
async def test_open_retries_exhausted_connection_with_matching_capped_backoff(monkeypatch, attempts):
    delays = record_backoff(monkeypatch, attempts)
    opened = []

    @asynccontextmanager
    async def unavailable():
        opened.append(asyncio.current_task())
        raise OSError("temporary transport failure")
        yield  # pragma: no cover

    monkeypatch.setattr(worker, "MCPTools", unavailable)
    async with AsyncExitStack() as stack:
        tools = worker.LazyMCP(stack)
        with pytest.raises(ToolFailure) as caught:
            await tools.open()
        assert tools.tools is None
    assert caught.value.code == "MCP_UNAVAILABLE"
    assert caught.value.retryable is True
    assert opened == [asyncio.current_task()] * attempts
    assert delays == [min(2 ** attempt, 2) for attempt in range(attempts - 1)]


async def test_temporary_open_failure_recovers_and_success_is_reused(monkeypatch):
    delays = record_backoff(monkeypatch, 3)
    opened, closed = [], []
    connected = object()

    @asynccontextmanager
    async def recovering():
        opened.append(asyncio.current_task())
        if len(opened) < 3:
            raise ToolFailure("MCP_UNAVAILABLE", "temporary failure", True)
        try:
            yield connected
        finally:
            closed.append(asyncio.current_task())

    monkeypatch.setattr(worker, "MCPTools", recovering)
    async with AsyncExitStack() as stack:
        tools = worker.LazyMCP(stack)
        await tools.open()
        await tools.open()
        assert tools.tools is connected
    assert delays == [1, 2]
    assert opened == [asyncio.current_task()] * 3
    assert closed == [asyncio.current_task()]


@pytest.mark.parametrize("retryable, expected_attempts", [(True, 3), (False, 1)])
async def test_typed_open_failure_keeps_code_retryability_and_identity(monkeypatch, retryable, expected_attempts):
    delays = record_backoff(monkeypatch, 3)
    failure = ToolFailure("MCP_UNAVAILABLE" if retryable else "MCP_AUTH_FAILED", "unavailable", retryable)
    opened = []

    @asynccontextmanager
    async def unavailable():
        opened.append(True)
        raise failure
        yield  # pragma: no cover

    monkeypatch.setattr(worker, "MCPTools", unavailable)
    async with AsyncExitStack() as stack:
        with pytest.raises(ToolFailure) as caught:
            await worker.LazyMCP(stack).open()
    assert caught.value is failure
    assert len(opened) == expected_attempts
    assert delays == ([1, 2] if retryable else [])


async def test_open_cancellation_is_not_retried_or_converted(monkeypatch):
    delays = record_backoff(monkeypatch, 3)
    opened = []

    @asynccontextmanager
    async def cancelled():
        opened.append(True)
        raise asyncio.CancelledError()
        yield  # pragma: no cover

    monkeypatch.setattr(worker, "MCPTools", cancelled)
    async with AsyncExitStack() as stack:
        with pytest.raises(asyncio.CancelledError):
            await worker.LazyMCP(stack).open()
    assert len(opened) == 1
    assert delays == []


@pytest.mark.parametrize("resume", [False, True])
async def test_exhaustion_preserves_checkpoint_then_delivery_recovers_without_reopening_on_replay(monkeypatch, resume):
    delays = record_backoff(monkeypatch, 3)
    tools, saver = SnapshotTools([[needs_review()]]), InMemorySaver()
    config = worker.checkpoint_config(tools.job)
    graph = worker.build_reclaim_graph(None, tools.job, saver)
    if resume:
        context = await tools.call("get_reclaim_check_context", {})
        await graph.aupdate_state(config, {
            "job": tools.job.model_dump(mode="json"), "context": context, "events": [],
        }, as_node="context")
    before = await graph.aget_state(config)
    calls_before = list(tools.calls)
    opened, closed = [], []
    owner = asyncio.current_task()

    class TaskBoundMCP:
        async def __aenter__(self):
            opened.append(asyncio.current_task())
            if len(opened) <= 3:
                raise OSError("temporary connection failure")
            self.scope = anyio.CancelScope()
            self.scope.__enter__()
            return self

        async def __aexit__(self, *args):
            closed.append(asyncio.current_task())
            self.scope.__exit__(*args)

        async def call(self, name, arguments):
            return await tools.call(name, arguments)

    monkeypatch.setattr(worker, "MCPTools", TaskBoundMCP)
    with pytest.raises(ToolFailure) as caught:
        await worker.run_job(tools.job, saver)
    assert caught.value.code == "MCP_UNAVAILABLE" and caught.value.retryable
    after = await graph.aget_state(config)
    assert after.config == before.config
    assert after.values == before.values and after.next == before.next
    assert "result_event" not in after.values
    assert tools.calls == calls_before
    assert delays == [1, 2]

    result = await worker.run_job(tools.job, saver)
    assert result["event_type"] == "RECLAIM_CHECKED"
    assert result["result"]["scan_complete"] is True
    assert opened == [owner] * 4 and closed == [owner]
    successful_calls = list(tools.calls)
    assert await worker.run_job(tools.job, saver) == result
    assert tools.calls == successful_calls
    assert opened == [owner] * 4 and closed == [owner]
