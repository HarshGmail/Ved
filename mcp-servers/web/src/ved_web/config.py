from pydantic_settings import BaseSettings, SettingsConfigDict

USER_AGENT = "Mozilla/5.0 (compatible; Ved/0.1; personal assistant)"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VED_", env_file=".env")

    searxng_url: str = "http://127.0.0.1:8888"
    search_timeout_seconds: float = 15.0
    search_default_limit: int = 5
    search_max_limit: int = 10

    fetch_timeout_seconds: float = 15.0
    fetch_max_bytes: int = 2_000_000
    fetch_max_characters: int = 12_000
    fetch_max_redirects: int = 5
    user_agent: str = USER_AGENT


settings = Settings()
