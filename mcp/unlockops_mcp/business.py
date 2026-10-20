"""직원·권한 조회와 승인된 변경 기능을 MCP 도구로 공개한다."""

from functools import lru_cache
import os

import uvicorn

from unlockops_rag.search import DocumentIndex
from .repository import Repository
from unlockops.rules import ceiling
from unlockops.settings import settings
from .auth import TokenAuth
from .contracts import APPROVED_WRITE, READ_ONLY, ContractMCP

HOST = os.getenv("MCP_HOST", "127.0.0.1")
PORT = int(os.getenv("MCP_PORT", "8002"))
mcp = ContractMCP(
    "unlockops-business", host=HOST, port=PORT, stateless_http=True, json_response=True
)
repo = Repository()


@lru_cache(maxsize=1)
def index():
    # 규정 인덱스는 재사용하고, 직원·로그인 예시가 있는 절은 검색에서 제외한다.
    """허용한 회사 권한 규정 절만 색인하고 프로세스에서 재사용한다."""
    return DocumentIndex(settings.data_dir / "company-a-access-matrix.md", "business", {3, 4, 7})


# 직원의 현재 소속·직급·직무를 정확한 ID로 조회한다.
@mcp.tool(annotations=READ_ONLY)
def get_employee_profile(employee_id: str) -> dict[str, object]:
    """직원 UUID로 소속 부서, 직급, 직무를 정확히 조회합니다. 로그인 비밀정보는 반환하지 않습니다."""
    return repo.profile(employee_id)


# 사용자 원문에 명시된 자원 후보를 반환한다. 후보가 여럿이면 Agent가 확정하지 않는다.
@mcp.tool(annotations=READ_ONLY)
def resolve_resource(platform: str, hint: str) -> dict[str, object]:
    """한 플랫폼 안에서 명시된 자원 후보를 찾습니다. 이름이 없거나 모호하면 임의로 추측하지 않습니다."""
    return repo.resolve(platform, hint)


# TF 구성원 여부와 해당 TF의 승인자를 확인한다.
@mcp.tool(annotations=READ_ONLY)
def get_tf_membership(employee_id: str, resource_id: str) -> dict[str, object]:
    """직원·자원 ID로 유효한 TF 구성원 여부와 해당 자원의 TF 리더를 조회합니다."""
    return repo.membership(employee_id, resource_id)


# 계획에 적힌 권한이 아니라 모의 SaaS에 실제 반영된 권한을 읽는다.
@mcp.tool(annotations=READ_ONLY)
def get_current_permissions(employee_id: str, resource_id: str) -> dict[str, object]:
    """모의 SaaS의 현재 권한을 조회합니다. GitHub는 제안된 권한이 아닌 실제 팀 멤버십을 확인합니다."""
    return repo.current(employee_id, resource_id)


# 유료 좌석을 검토할 때 부서 잔여 예산과 가격을 읽는다.
@mcp.tool(annotations=READ_ONLY)
def check_budget(employee_id: str) -> dict[str, object]:
    """직원 소속 부서의 잔여 월 예산과 모의 유료 좌석 가격을 조회합니다."""
    budget = repo.budget(employee_id)
    return {"budget": budget}


# 회사 규정 검색 근거와 코드로 계산한 직무·직급별 상한을 함께 반환한다.
@mcp.tool(annotations=READ_ONLY)
def search_access_rules(query: str, employee_id: str, resource_id: str) -> dict[str, object]:
    """회사 권한 문서의 근거와 직원의 직급·직무·자원 기준에 따른 허용 상한을 조회합니다."""
    profile, resource = repo.profile(employee_id), repo.resource(resource_id)
    return {
        "hits": index().search(query, limit=6),
        "maximum_role": ceiling(profile, resource),
        "rule_source": "A-ACCESS-03",
        "exception_source": "A-ACCESS-04",
    }


# 유사도 검색으로 놓칠 수 있는 필수 회사 규정 절을 ID로 직접 읽는다.
@mcp.tool(annotations=READ_ONLY)
def read_access_rule(doc_id: str) -> dict[str, object]:
    """회사 권한 문서의 지정된 절을 원문으로 읽습니다. 초안 상태 등 출처 메타데이터도 반환합니다."""
    return {"chunks": index().read(doc_id)}


# 유일한 변경 도구. 대상·역할을 새로 받지 않고 DB의 승인 계획을 실행한다.
@mcp.tool(annotations=APPROVED_WRITE)
def grant_permission(problem_id: str, idempotency_key: str) -> dict[str, object]:
    """DB에 저장된 사람 승인 완료 계획만 실행합니다. 요청자, 승인자, 부여 자격, 예산을 다시 확인합니다.

    호출자가 직원·자원·역할을 임의로 지정할 수 없습니다. 모의 Jira의 일시 장애는 재시도할 수 있지만,
    승인이나 사전조건 검증 실패는 재시도하지 않습니다. 실행 영수증으로 중복 전달에 따른 중복 변경을 막습니다.
    """
    return repo.grant(problem_id, idempotency_key)


# 부여 뒤 다시 조회하는 검증 도구도 읽기 전용이다.
@mcp.tool(annotations=READ_ONLY)
def verify_permission(employee_id: str, resource_id: str, requested_role: str) -> dict[str, object]:
    """실행 후 실제 유효 권한을 별도로 다시 조회합니다. 필요한 권한이 없으면 verified=false를 반환합니다."""
    return repo.verify(employee_id, resource_id, requested_role)


if __name__ == "__main__":
    uvicorn.run(TokenAuth(mcp.streamable_http_app()), host=HOST, port=PORT)
