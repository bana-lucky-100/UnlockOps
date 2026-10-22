"""환경변수와 실행 한도를 한곳에서 읽는다. 비밀값은 루트 .env로 주입한다."""

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env", override=False)


def project_path(name: str, default: str) -> Path:
    """터미널의 실행 위치가 달라도 프로젝트 기준으로 경로를 해석한다."""
    path = Path(os.getenv(name) or default).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class Settings:
    """실행 중에는 설정을 변경하지 않는 데이터 묶음."""

    mode: str = os.getenv("AGENT_MODE", "demo")
    data_dir: Path = project_path("DATA_DIR", "data")
    checkpoint_path: str = str(
        project_path("CHECKPOINT_PATH", "data/checkpoints/checkpoints.sqlite")
    )
    policy_url: str = os.getenv("POLICY_MCP_URL", "http://localhost:8001/mcp")
    business_url: str = os.getenv("BUSINESS_MCP_URL", "http://localhost:8002/mcp")
    mcp_token: str = os.getenv("MCP_TOKEN", "replace-this-local-mcp-token")
    backend_url: str = os.getenv("BACKEND_INTERNAL_URL", "http://localhost:8080")
    internal_api_token: str = os.getenv("INTERNAL_API_TOKEN", "replace-this-local-internal-api-token")
    rabbit_url: str = os.getenv("RABBIT_URL") or os.getenv("RABBITMQ_URL", "")
    tool_timeout: float = 15
    max_tools: int = 30
    max_optional_tools: int = 10
    max_model_steps: int = 4
    max_execution_attempts: int = 3  # 최초 1회 + 재시도 2회
    max_verification_attempts: int = 3


settings = Settings()
