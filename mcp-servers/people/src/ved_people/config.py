from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="VED_", env_file=".env")

    database_url: str = "postgresql+psycopg://ved:ved@localhost:5432/ved"
    timezone: str = "Asia/Kolkata"
    max_notice_days: int = 60


settings = Settings()
