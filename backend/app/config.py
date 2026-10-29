"""Runtime configuration, read from environment variables (and an optional .env file).

Never log or print the API key.
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env", ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- Meta Model API (see docs/meta-api-notes.md) ---
    model_api_key: SecretStr | None = Field(default=None, alias="MODEL_API_KEY")
    meta_base_url: str = Field(default="https://api.meta.ai/v1", alias="META_BASE_URL")
    vision_model: str = Field(default="muse-spark-1.3", alias="SIFT_VISION_MODEL")
    text_model: str = Field(default="muse-spark-1.3", alias="SIFT_TEXT_MODEL")
    transcribe_model: str = Field(default="muse-voice-transcribe-1.0", alias="SIFT_TRANSCRIBE_MODEL")
    segment_model: str = Field(default="sam-3.1", alias="SIFT_SEGMENT_MODEL")
    request_timeout_s: float = Field(default=45.0, alias="SIFT_REQUEST_TIMEOUT_S")

    # Optional: run text-only calls on the open-weight Muse Spark Open via Baseten.
    open_weight_text: bool = Field(default=False, alias="SIFT_OPEN_WEIGHT_TEXT")
    baseten_api_key: SecretStr | None = Field(default=None, alias="BASETEN_API_KEY")
    baseten_base_url: str = Field(
        default="https://inference.baseten.co/v1", alias="BASETEN_BASE_URL"
    )
    open_weight_model: str = Field(
        default="meta-models/muse-spark-open-1026", alias="SIFT_OPEN_WEIGHT_MODEL"
    )

    # Offline development mode: deterministic fake model responses, clearly flagged in the UI.
    mock_meta: bool = Field(default=False, alias="SIFT_MOCK_META")

    # --- Pipeline ---
    db_path: str = Field(default=str(REPO_ROOT / "backend" / "sift_session.db"), alias="SIFT_DB")
    worker_concurrency: int = Field(default=3, alias="SIFT_WORKERS")
    queue_max: int = Field(default=12, alias="SIFT_QUEUE_MAX")
    stale_after_s: float = Field(default=45.0, alias="SIFT_STALE_AFTER_S")
    dedup_max_distance: int = Field(default=6, alias="SIFT_DEDUP_DISTANCE")

    @property
    def meta_enabled(self) -> bool:
        return self.mock_meta or self.model_api_key is not None


@lru_cache
def get_settings() -> Settings:
    return Settings()
