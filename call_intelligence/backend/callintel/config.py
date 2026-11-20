"""Settings, read from the environment (and a .env file in development)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+psycopg://callintel:callintel-local@localhost:5432/callintel"
    jwt_secret: str = "change-me-in-production"
    jwt_hours: int = 12
    # keyed hash for phone numbers (stored hashed + masked; the full number only for permitted roles)
    phone_hash_key: str = "change-me-too"

    # recordings: a local folder (a mounted volume in Docker)
    storage_dir: str = "./data/recordings"
    max_upload_mb: int = 200

    # models on the DGX gateway (OpenAI-compatible, Open WebUI)
    llm_api_url: str = "https://llm-api.gcp.trysia.ai/api"
    llm_api_key: str = ""
    llm_model: str = "qwen3.6-35b"
    llm_second_opinion_model: str = ""          # e.g. "gemma4-26b" once the gateway exposes it; "" = second Qwen pass
    embedding_model: str = "qwen3-embedding-4b"
    llm_timeout_s: float = 180.0

    # transcription service (Mohammed's fine-tuned Cohere model + pyannote), see asr_service/
    asr_service_url: str = ""                  # "" = no service: uploads wait in "waiting for transcription"

    # worker
    worker_poll_s: float = 2.0
    worker_concurrency: int = 2

    # first admin, created on an empty database
    admin_email: str = "admin@trysia.ai"
    admin_password: str = "admin-change-me"

    frontend_dir: str = "../frontend/dist"


@lru_cache
def settings() -> Settings:
    return Settings()
