from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VED_", env_file=".env")

    database_url: str = "postgresql+psycopg://ved:ved@localhost:5432/ved"
    llm_base_url: str = "http://localhost:11434/v1"
    llm_api_key: str | None = None
    embedding_model: str = "nomic-embed-text"
    embedding_dimensions: int = 768
    embedding_timeout_seconds: float = 60.0
    embedding_query_prefix: str = "search_query: "
    search_default_limit: int = 5
    search_max_limit: int = 20
    documents_list_limit: int = 100


settings = Settings()
