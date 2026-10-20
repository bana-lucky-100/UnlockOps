from functools import lru_cache
import os

from mcp.server.fastmcp import FastMCP
import uvicorn

from unlockops_rag.search import DocumentIndex
from .repository import Repository
from unlockops.rules import ceiling
from unlockops.settings import settings
from .auth import TokenAuth

HOST = os.getenv("MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("MCP_PORT", "8002"))
mcp = FastMCP("unlockops-business", host=HOST, port=PORT, stateless_http=True, json_response=True)
repo = Repository()


@lru_cache
def index():
    # Employee/sample-login sections are not sent to the model as RAG context.
    return DocumentIndex(settings.data_dir / "company-a-access-matrix.md", "business", {3, 4, 7})


@mcp.tool()
def get_employee_profile(employee_id: str) -> dict:
    """Exact employee lookup by UUID: department, grade and job family. Never returns login secrets."""
    return repo.profile(employee_id)


@mcp.tool()
def resolve_resource(platform: str, hint: str) -> dict:
    """Resolve an explicitly named resource within ONE platform; an empty/ambiguous name is not guessed."""
    return repo.resolve(platform, hint)


@mcp.tool()
def get_tf_membership(employee_id: str, resource_id: str) -> dict:
    """Return active TF membership and the resource TF leader using exact IDs."""
    return repo.membership(employee_id, resource_id)


@mcp.tool()
def get_current_permissions(employee_id: str, resource_id: str) -> dict:
    """Read actual mock SaaS access; GitHub is checked via team memberships, not a proposed permission."""
    return repo.current(employee_id, resource_id)


@mcp.tool()
def check_budget(employee_id: str) -> dict:
    """Read the employee department's remaining monthly budget and simulated seat price."""
    budget = repo.budget(employee_id)
    return {"budget": budget}


@mcp.tool()
def search_access_rules(query: str, employee_id: str, resource_id: str) -> dict:
    """Retrieve company matrix evidence and the explicit grade/job/resource ceiling for this employee."""
    profile, resource = repo.profile(employee_id), repo.resource(resource_id)
    return {"hits": index().search(query, limit=6),
            "maximum_role": ceiling(profile, resource),
            "rule_source": "A-ACCESS-03", "exception_source": "A-ACCESS-04"}


@mcp.tool()
def read_access_rule(doc_id: str) -> dict:
    """Read a known section of the company access matrix exactly, including its draft metadata."""
    return {"chunks": index().read(doc_id)}


@mcp.tool()
def grant_permission(problem_id: str, idempotency_key: str) -> dict:
    """Execute only the immutable, human-approved DB plan. Recheck identity, approver, eligibility and budget.

    Caller cannot supply an arbitrary employee/resource/role. Simulated Jira outages are retryable;
    approval and precondition failures are not. A receipt makes repeated deliveries idempotent.
    """
    return repo.grant(problem_id, idempotency_key)


@mcp.tool()
def verify_permission(employee_id: str, resource_id: str, requested_role: str) -> dict:
    """Independently re-read effective access after execution; return verified=false when absent."""
    return repo.verify(employee_id, resource_id, requested_role)


if __name__ == "__main__":
    uvicorn.run(TokenAuth(mcp.streamable_http_app()), host=HOST, port=PORT)
