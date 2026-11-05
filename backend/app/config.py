"""Application settings, read from the environment. No secret has a production default."""

from functools import lru_cache
from pathlib import Path

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_SECRET = "dev-only-secret-not-for-production"  # noqa: S105 - rejected in production below


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_base_url: str = "http://localhost:3000"
    secret_key: str = _DEV_SECRET
    database_url: str = "postgresql+psycopg://medicompare:devpassword@localhost:5433/medicompare"
    redis_url: str = "redis://localhost:6380/0"
    s3_endpoint_url: str | None = "http://localhost:9010"
    s3_access_key: str = "devminioaccess"
    s3_secret_key: str = "devminiosecret"  # noqa: S105 - local-only default
    s3_bucket: str = "medicompare-prescriptions"
    s3_region: str = "ap-south-1"
    signed_url_seconds: int = 300
    retention_days: int = 7
    ocr_engine: str = "tesseract"
    include_demo_data: bool = True
    llm_extraction_enabled: bool = False
    llm_api_key: str = ""
    llm_model: str = ""
    clamav_address: str = ""
    cookie_secure: bool = False
    session_hours: int = 24 * 7
    guest_session_hours: int = 24 * 7
    share_link_days: int = 7
    max_upload_bytes: int = 10 * 1024 * 1024
    max_pdf_pages: int = 5
    min_image_side: int = 200
    max_image_pixels: int = 40_000_000
    login_max_failures: int = 5
    login_lock_minutes: int = 15
    rate_limit_enabled: bool = True
    rate_limit_public_per_minute: int = 300
    rate_limit_auth_per_minute: int = 20
    rate_limit_upload_per_hour: int = 30
    jobs_synchronous: bool = False
    data_dir: str = str(Path(__file__).resolve().parents[2] / "data")
    log_level: str = "INFO"

    @model_validator(mode="after")
    def _production_requires_real_secrets(self) -> "Settings":
        if self.app_env == "production":
            if self.secret_key == _DEV_SECRET or len(self.secret_key) < 32:
                raise ValueError(
                    "SECRET_KEY must be a unique value of 32+ characters in production"
                )
            if not self.cookie_secure:
                raise ValueError("COOKIE_SECURE must be true in production")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
