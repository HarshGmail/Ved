from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_API_URL = "https://photos.my-finances.site/api"
DEFAULT_PUBLIC_URL = "https://photos.my-finances.site"
REQUEST_TIMEOUT_SECONDS = 15.0


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SNAPPY_", env_file=".env", extra="ignore"
    )

    api_url: str = DEFAULT_API_URL
    public_url: str = DEFAULT_PUBLIC_URL
    request_timeout_seconds: float = REQUEST_TIMEOUT_SECONDS


settings = Settings()
