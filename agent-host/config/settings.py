import socket

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    controller_url: str              # https://ocp.pontium.org
    ollama_url: str = "http://host.docker.internal:11434"
    invitation_token: str = ""       # 初回登録用（登録後は不要）
    poll_interval: int = 30          # Controllerから上書き可能
    max_concurrent_jobs: int = 1
    hostname: str = socket.gethostname()
    config_dir: str = "/app/data"    # 永続設定保存ディレクトリ


settings = Settings()
