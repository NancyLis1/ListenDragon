from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:////data/listendragon.db"
    data_root: str = "/data"
    max_upload_mb: int = 500
    max_video_minutes: int = 60
    worker_poll_seconds: float = 2.0
    worker_concurrency: int = 1
    cors_origins: str = "http://localhost:5173"
    asr_model: str = "base"
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
