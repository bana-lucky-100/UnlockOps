"""Current policy MCP server; one workflow tool surface."""
import os
import uvicorn
from .auth import TokenAuth
from .contracts import ContractMCP
from .policy_tools import register

HOST = os.getenv("MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("MCP_PORT", "8001"))
mcp = ContractMCP("unlockops-policy", host=HOST, port=PORT, stateless_http=True, json_response=True)
tools = register(mcp)

if __name__ == "__main__":
    uvicorn.run(TokenAuth(mcp.streamable_http_app()), host=HOST, port=PORT)
