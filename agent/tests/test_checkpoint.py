from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from langgraph.types import Command

from unlockops.access.graph import build_graph
from unlockops.common.models import Plan
from conftest import FakeTools
from test_scenarios import job


async def test_persistent_checkpoint_survives_graph_and_connection_recreation(tmp_path):
    path=str(tmp_path/"checkpoints.sqlite")
    config={"configurable":{"thread_id":"durable-request"}}
    tools=FakeTools()
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        graph=build_graph(tools,saver)
        await graph.ainvoke({"job":job("GITHUB","payment-core push가 안 돼요"),"events":[]},config)
    tools.approved=True
    async with AsyncSqliteSaver.from_conn_string(path) as saver:
        graph=build_graph(tools,saver)
        saved=await graph.aget_state(config)
        assert saved.values["result"]["status"]=="WAITING_APPROVAL"
        result=await graph.ainvoke(Command(resume={"approved":True,"plan_hash":Plan.model_validate(saved.values["plan"]).digest(),"idempotency_key":"durable-key"}),config)
        assert result["result"]["status"]=="DONE"
        assert tools.writes==1
