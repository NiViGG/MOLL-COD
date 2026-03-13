"""Centralized configuration."""
import os
from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "HARLEY-AI"
    version: str = "1.0.0"
    debug: bool = False
    environment: str = "production"

    host: str = "0.0.0.0"
    port: int = 8000

    redis_url: str = "redis://redis:6379/0"
    redis_password_file: Path = Path("/run/secrets/redis_password")

    jwt_secret_file: Path = Path("/run/secrets/jwt_secret")
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24h
    rate_limit_per_minute: int = 120

    base_dir: Path = Path("/app")
    logs_dir: Path = Path("/app/logs")
    knowledge_dir: Path = Path("/app/knowledge")
    versions_dir: Path = Path("/app/versions")
    updates_dir: Path = Path("/app/updates")
    certs_dir: Path = Path("/app/certs")
    static_dir: Path = Path("/app/static")
    uploads_dir: Path = Path("/app/uploads")

    # Ollama
    ollama_url: str = "http://ollama:11434"
    ollama_model: str = "llama3.2"
    ollama_vision_model: str = "llava"
    ollama_embed_model: str = "nomic-embed-text"

    # Whisper
    whisper_model: str = "base"  # tiny/base/small/medium/large

    # Harley character
    harley_personality: str = "harley_quinn"
    max_context_messages: int = 20

    log_level: str = "INFO"
    sandbox_timeout_seconds: int = 30
    sandbox_max_output_chars: int = 10_000
    max_upload_mb: int = 50

    class Config:
        env_file = ".env"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

for _d in (
    settings.logs_dir, settings.knowledge_dir, settings.versions_dir,
    settings.updates_dir, settings.static_dir, settings.uploads_dir,
):
    _d.mkdir(parents=True, exist_ok=True)
