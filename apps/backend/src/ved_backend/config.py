from pydantic_settings import BaseSettings, SettingsConfigDict

LOCAL_DATABASE_URL = "postgresql+psycopg://ved:ved@localhost:5432/ved"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VED_", env_file=".env")

    version: str = "0.1.0"
    cors_allow_origins: list[str] = ["http://localhost:3000"]
    database_url: str = LOCAL_DATABASE_URL
    database_pool_size: int = 5
    database_pool_max_overflow: int = 5


settings = Settings()
