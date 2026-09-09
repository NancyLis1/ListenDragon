from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    log_level: str = "INFO"
    database_url: str = "sqlite:////data/listendragon.db"
    data_root: str = "/data"
    max_upload_mb: int = Field(default=500, gt=0)
    max_video_minutes: int = Field(default=60, gt=0)
    worker_poll_seconds: float = 2.0
    worker_concurrency: int = 1
    worker_video_id: str | None = None
    worker_lease_seconds: int = 30 * 60
    ffmpeg_binary: str = "ffmpeg"
    ffprobe_binary: str = "ffprobe"
    cors_origins: str = "http://localhost:5173"
    asr_model: str = "base"
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"
    chunk_min_chars: int = 300
    chunk_target_chars: int = 400
    chunk_max_chars: int = 500
    chunk_overlap_chars: int = 50
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    llm_base_url: str | None = None
    llm_api_key: str | None = None
    llm_model: str | None = None
    vision_enabled: bool = True
    vision_model: str | None = None
    vision_interval_seconds: float = Field(default=0.5, ge=0.25, le=10)
    vision_max_frames: int = Field(default=24, ge=4, le=24)
    vision_window_seconds: float = Field(default=12, ge=4, le=30)
    vision_scene_detection: bool = True
    vision_max_windows: int = Field(default=180, ge=1, le=600)
    vision_short_video_seconds: float = Field(default=90, ge=10, le=180)
    retrieval_top_k: int = Field(default=8, ge=1, le=100)
    retrieval_rrf_k: int = Field(default=60, ge=1)
    query_expansion_enabled: bool = True
    query_expansion_timeout_seconds: float = Field(default=8.0, gt=0, le=60)
    llm_timeout_seconds: float = Field(default=30.0, gt=0, le=120)
    llm_max_response_bytes: int = Field(default=1024 * 1024, ge=4096, le=4 * 1024 * 1024)
    generation_context_chars: int = Field(default=24000, ge=4000, le=120000)
    conversation_memory_chars: int = Field(default=1200, ge=200, le=4000)

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
