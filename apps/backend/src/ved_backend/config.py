from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_DATABASE_URL = "postgresql+psycopg://ved:ved@localhost:5432/ved"
REPO_ROOT = Path(__file__).resolve().parents[4]
REMINDERS_SERVER_DIR = REPO_ROOT / "mcp-servers" / "reminders"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VED_", env_file=".env")

    version: str = "0.1.0"
    cors_allow_origins: list[str] = ["http://localhost:3000"]
    database_url: str = LOCAL_DATABASE_URL
    database_pool_size: int = 5
    database_pool_max_overflow: int = 5

    llm_provider: str = "stub"
    timezone: str = "Asia/Kolkata"
    agent_max_tool_rounds: int = 4

    conversation_history_limit: int = 20
    conversation_list_limit: int = 50

    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen3.6:35b"
    llm_api_key: str | None = None
    llm_timeout_seconds: float = 120.0
    llm_temperature: float | None = 0.0

    reminders_server_command: str = "uv"
    reminders_server_args: list[str] = ["run", "ved-mcp-reminders"]
    reminders_server_dir: str = str(REMINDERS_SERVER_DIR)


settings = Settings()
