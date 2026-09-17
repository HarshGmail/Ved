from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VED_", env_file=".env")

    version: str = "0.1.0"
    cors_allow_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
