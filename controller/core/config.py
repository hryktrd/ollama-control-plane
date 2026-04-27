from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str = "sqlite+aiosqlite:///./data/controller.db"
    controller_secret: str
    jwt_algorithm: str = "HS256"
    listener_token_ttl_hours: int = 2
    poll_timeout_seconds: int = 30
    job_timeout_seconds: int = 300
    admin_api_key: str


settings = Settings()
