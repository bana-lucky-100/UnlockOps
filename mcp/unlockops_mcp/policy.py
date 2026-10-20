from functools import lru_cache
import os

from mcp.server.fastmcp import FastMCP
import uvicorn

from unlockops_rag.search import DocumentIndex
from unlockops.settings import settings
from .auth import TokenAuth

HOST = os.getenv("MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("MCP_PORT", "8001"))
mcp = FastMCP("unlockops-policy", host=HOST, port=PORT, stateless_http=True, json_response=True)


@lru_cache
def index():
    return DocumentIndex(settings.data_dir / "policy_corpus.md", "policy")


@mcp.tool()
def search_policy(query: str, platform: str, limit: int = 5) -> dict:
    """Search common and platform policy articles; return original text and source/version metadata."""
    if platform not in {"GITHUB", "JIRA", "SLACK", "NOTION"}: raise ValueError("Unknown platform")
    return {"hits": index().search(query, platform, limit)}


@mcp.tool()
def read_policy(doc_id: str, article: str = "") -> dict:
    """Read a known policy document/article exactly. A document ID is not a filesystem path."""
    return {"chunks": index().read(doc_id, article)}


if __name__ == "__main__":
    uvicorn.run(TokenAuth(mcp.streamable_http_app()), host=HOST, port=PORT)
