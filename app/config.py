"""
OmniCrew AI — Centralized configuration via Pydantic Settings.

All configuration is driven by environment variables with the ``OMNICREW_`` prefix.
Secrets are never hard-coded; they must be supplied through env vars or a ``.env``
file placed at the project root.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application-wide configuration sourced from environment variables.

    Every field uses a descriptive ``Field(...)`` with explicit constraints so
    that mis-configuration fails fast at startup rather than at runtime.
    """

    model_config = SettingsConfigDict(
        env_prefix="OMNICREW_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── LLM / GenAI ──────────────────────────────────────────────────────
    google_api_key: SecretStr = Field(
        ...,
        description="Google Gemini API key.  Required for LLM inference.",
    )
    llm_model_name: str = Field(
        default="gemini-2.0-flash",
        max_length=64,
        description="Name of the Gemini model to use for inference.",
    )
    llm_temperature: float = Field(
        default=0.2,
        ge=0.0,
        le=1.0,
        description="Sampling temperature for the LLM (0 = deterministic).",
    )

    # ── Authentication ────────────────────────────────────────────────────
    firebase_project_id: str = Field(
        default="omnicrew-ai-2026",
        max_length=64,
        description="Firebase project ID for Auth token verification.",
    )
    allowed_roles: list[str] = Field(
        default=["medic", "usher", "security", "command-center"],
        description="Set of valid staff roles for RBAC enforcement.",
    )

    # ── Edge / IoT Thresholds ─────────────────────────────────────────────
    edge_crowd_threshold: int = Field(
        default=800,
        ge=100,
        le=5000,
        description="Turnstile count above which a crowd-density alert fires.",
    )
    edge_temperature_max_c: float = Field(
        default=42.0,
        ge=20.0,
        le=60.0,
        description="Temperature (°C) above which a heat-alert fires.",
    )

    # ── Server ────────────────────────────────────────────────────────────
    server_host: str = Field(
        default="0.0.0.0",
        description="Host address for the Uvicorn ASGI server.",
    )
    server_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description="Port number for the Uvicorn ASGI server.",
    )

    # ── Rate Limiting ─────────────────────────────────────────────────────
    rate_limit_rpm: int = Field(
        default=60,
        ge=1,
        le=10000,
        description="Maximum requests per minute per API key.",
    )

    # ── Crypto ────────────────────────────────────────────────────────────
    hmac_secret: str = Field(
        default="omnicrew-dev-secret",
        min_length=8,
        description="HMAC secret used for API-key hashing.  Override in prod!",
    )

    # ── Helpers ───────────────────────────────────────────────────────────

    @field_validator("allowed_roles", mode="before")
    @classmethod
    def _parse_roles(cls, v: Any) -> list[str]:
        """Accept a comma-separated string or a list."""
        if isinstance(v, str):
            return [r.strip() for r in v.split(",") if r.strip()]
        return v  # type: ignore[return-value]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached singleton ``Settings`` instance.

    Using ``@lru_cache`` avoids re-parsing env vars on every request while
    keeping the function signature simple enough for FastAPI's dependency
    injection.
    """
    return Settings()  # type: ignore[call-arg]
