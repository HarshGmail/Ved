from datetime import time
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_DATABASE_URL = "postgresql+psycopg://ved:ved@localhost:5432/ved"
REPO_ROOT = Path(__file__).resolve().parents[4]
REMINDERS_SERVER_DIR = REPO_ROOT / "mcp-servers" / "reminders"
PEOPLE_SERVER_DIR = REPO_ROOT / "mcp-servers" / "people"
MEMORY_SERVER_DIR = REPO_ROOT / "mcp-servers" / "memory"
WEB_SERVER_DIR = REPO_ROOT / "mcp-servers" / "web"
LOCAL_SEARXNG_URL = "http://127.0.0.1:8888"
NOMIC_DOCUMENT_PREFIX = "search_document: "
NOMIC_QUERY_PREFIX = "search_query: "


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VED_", env_file=".env")

    version: str = "0.1.0"
    cors_allow_origins: list[str] = ["http://localhost:3000"]
    database_url: str = LOCAL_DATABASE_URL
    database_pool_size: int = 5
    database_pool_max_overflow: int = 5

    llm_provider: str = "stub"
    timezone: str = "Asia/Kolkata"
    agent_max_tool_rounds: int = 8

    conversation_history_limit: int = 20
    conversation_list_limit: int = 50

    vapid_public_key: str | None = None
    vapid_private_key: str | None = None
    vapid_subject: str = "mailto:ved@example.com"
    scheduler_poll_seconds: float = 30.0
    birthday_reminder_time: time = time(9, 0)

    llm_base_url: str = "http://localhost:11434/v1"
    llm_model: str = "qwen3.6:35b"
    llm_api_key: str | None = None
    llm_timeout_seconds: float = 120.0
    llm_temperature: float | None = 0.0

    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768
    embedding_timeout_seconds: float = 60.0
    embedding_document_prefix: str = NOMIC_DOCUMENT_PREFIX
    embedding_query_prefix: str = NOMIC_QUERY_PREFIX

    reminders_server_command: str = "uv"
    reminders_server_args: list[str] = ["run", "ved-mcp-reminders"]
    reminders_server_dir: str = str(REMINDERS_SERVER_DIR)

    people_server_command: str = "uv"
    people_server_args: list[str] = ["run", "ved-mcp-people"]
    people_server_dir: str = str(PEOPLE_SERVER_DIR)

    memory_server_command: str = "uv"
    memory_server_args: list[str] = ["run", "ved-mcp-memory"]
    memory_server_dir: str = str(MEMORY_SERVER_DIR)

    web_server_command: str = "uv"
    web_server_args: list[str] = ["run", "ved-mcp-web"]
    web_server_dir: str = str(WEB_SERVER_DIR)
    searxng_url: str = LOCAL_SEARXNG_URL


settings = Settings()
