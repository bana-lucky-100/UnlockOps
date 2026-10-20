import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env", override=False)


def project_path(name: str, default: str) -> Path:
    path = Path(os.getenv(name) or default).expanduser()
    return path if path.is_absolute() else PROJECT_ROOT / path


@dataclass(frozen=True)
class Settings:
    mode: str = os.getenv("AGENT_MODE", "demo")
    data_dir: Path = project_path("DATA_DIR", "data")
    checkpoint_path: str = str(project_path("CHECKPOINT_PATH", "data/checkpoints/checkpoints.sqlite"))
    policy_url: str = os.getenv("POLICY_MCP_URL", "http://localhost:8001/mcp")
    business_url: str = os.getenv("BUSINESS_MCP_URL", "http://localhost:8002/mcp")
    mcp_token: str = os.getenv("MCP_TOKEN", "replace-this-local-mcp-token")
    database_url: str = os.getenv("DATABASE_URL", "")
    rabbit_url: str = os.getenv("RABBIT_URL") or os.getenv("RABBITMQ_URL", "")
    tool_timeout: float = 15
    max_tools: int = 30
    max_model_steps: int = 4
    max_execution_attempts: int = 3  # Initial attempt + two retries.


settings = Settings()
