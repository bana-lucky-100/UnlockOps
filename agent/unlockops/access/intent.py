"""Platform aliases and single-platform request interpretation."""
import re
from .planner import interpret

ALIASES = {
    'GITHUB': r'github|copilot|깃허브|코파일럿', 'JIRA': r'jira|지라',
    'SLACK': r'slack|슬랙', 'NOTION': r'notion|노션',
    'SNOWFLAKE': r'snowflake|스노우플레이크', 'DATABRICKS': r'databricks|데이터브릭스',
    'SALESFORCE': r'salesforce|세일즈포스', 'DATADOG': r'datadog|데이터독',
    'TABLEAU_CLOUD': r'tableau(?: cloud)?|태블로', 'FIGMA': r'figma|피그마',
}


def scoped_text(text, platform):
    mentions = sorted((m.start(), key) for key, aliases in ALIASES.items()
                      for m in re.finditer(r'(?<![a-z])(?:' + aliases + r')(?![a-z])', text, re.I))
    if not mentions:
        return text
    first = mentions[0][1]
    if first != platform:
        from ..common.models import ToolFailure
        raise ToolFailure('OUT_OF_SCOPE', 'First platform differs from stored request scope')
    end = next((pos for pos, key in mentions if key != first), len(text))
    return text[:end]


async def interpret_v4(contents, platform):
    text = scoped_text(contents, platform)
    if re.search(r'부서\s*이동|일괄\s*승인|(?:\bdb\b|데이터베이스)\s*배포', text, re.I):
        from ..common.models import ToolFailure
        raise ToolFailure('OUT_OF_SCOPE', 'Operation is outside the scenario-v4 permission workflow')
    return await interpret(text, platform)


ROLE_ALIASES = {
    'SNOWFLAKE': {'usage': 'ANALYST', 'warehouse usage': 'ANALYST'},
    'DATABRICKS': {'can edit': 'NOTEBOOK_JOB_USER', 'can manage run': 'NOTEBOOK_JOB_USER'},
    'SALESFORCE': {'can edit': 'ASSIGNED_CUSTOMER_EDITOR', 'edit': 'ASSIGNED_CUSTOMER_EDITOR'},
    'DATADOG': {'read': 'SERVICE_VIEWER', 'read only': 'SERVICE_VIEWER', 'viewer': 'SERVICE_VIEWER'},
    'TABLEAU_CLOUD': {'can edit': 'PROJECT_PUBLISHER', 'explorer': 'PROJECT_PUBLISHER'},
    'FIGMA': {'can edit': 'EDITOR_SEAT', 'full': 'EDITOR_SEAT'},
    'NOTION': {'can edit': 'EDITOR'},
}


def read_is_sufficient(text):
    purpose = any(x in text.casefold() for x in ('코드 열람', '코드 조회', '읽기 전용', 'read-only', 'read only'))
    changes = any(x in text.casefold() for x in ('push', 'write', '편집', '수정', '삭제', '설정', '배포'))
    return purpose and not changes
