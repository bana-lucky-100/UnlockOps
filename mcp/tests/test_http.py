"""MCP HTTP lifespan/authentication checks; no DB or external model calls."""
import pytest
from starlette.testclient import TestClient

from unlockops.settings import settings
from unlockops_mcp.auth import TokenAuth
from unlockops_mcp.business import mcp as business_mcp
from unlockops_mcp.policy import mcp as policy_mcp


@pytest.mark.parametrize("server", [policy_mcp, business_mcp])
def test_server_starts_and_requires_token_for_discovery(server):
    with TestClient(TokenAuth(server.streamable_http_app()), base_url="http://127.0.0.1:8000") as client:
        assert client.get("/health").status_code == 401
        headers = {"Authorization": "Bearer " + settings.mcp_token}
        assert client.get("/health", headers=headers).json() == {"status": "UP"}
        assert client.post("/mcp", json={}).status_code == 401
        headers.update({"Accept": "application/json, text/event-stream"})
        response = client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                       "clientInfo": {"name": "layout-test", "version": "1"}},
        })
        assert response.status_code == 200
        assert response.json()["result"]["serverInfo"]["name"].startswith("unlockops-")
        response = client.post("/mcp", headers=headers, json={
            "jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {},
        })
        assert response.status_code == 200
        names = {tool["name"] for tool in response.json()["result"]["tools"]}
        expected = {"search_policy", "read_policy"} if server is policy_mcp else {
            "get_employee_profile", "grant_permission", "verify_permission"}
        assert names >= expected
