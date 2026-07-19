"""
OmniCrew AI — Shared FastAPI dependencies.

Provides injectable components for authentication (Firebase ID token
verification), rate limiting, LLM instantiation, and edge telemetry
access.  All dependencies are designed for test-time override via
``app.dependency_overrides``.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.config import get_settings
from app.edge.stream import EdgeStreamConsumer

logger = logging.getLogger(__name__)

# ── Firebase Auth ───────────────────────────────────────────────────────


class StaffUser(BaseModel):
    """Authenticated staff identity extracted from a Firebase ID token."""

    uid: str = Field(
        ...,
        min_length=1,
        description="Firebase user ID.",
    )
    email: str = Field(
        ...,
        description="Staff member's email address.",
    )
    role: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Staff role: medic, usher, security, or command-center.",
    )
    gate: str = Field(
        default="",
        max_length=64,
        description="Assigned gate/location from custom claims.",
    )


async def verify_firebase_token(request: Request) -> StaffUser:
    """Verify the Firebase ID token from the Authorization header.

    Reads the ``Authorization: Bearer <token>`` header, verifies the
    token via Firebase Admin SDK, and extracts the user's role from
    custom claims.

    Raises:
        HTTPException 401: Missing, malformed, or invalid token.
        HTTPException 403: Token valid but no role claim assigned.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or malformed Authorization header. Expected: Bearer <token>",
        )

    token = auth_header[7:]  # Strip "Bearer "

    try:
        from firebase_admin import auth

        decoded = auth.verify_id_token(token)
    except Exception as exc:
        logger.warning("Firebase token verification failed: %s", exc)
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired authentication token.",
        )

    uid = decoded.get("uid", "")
    email = decoded.get("email", "")
    role = decoded.get("role", "")
    gate = decoded.get("gate", "")

    if not role:
        raise HTTPException(
            status_code=403,
            detail="No role assigned to this account. Contact your administrator.",
        )

    settings = get_settings()
    if role not in settings.allowed_roles:
        raise HTTPException(
            status_code=403,
            detail=f"Role '{role}' is not permitted.",
        )

    return StaffUser(uid=uid, email=email, role=role, gate=gate)


# ── Rate Limiter ────────────────────────────────────────────────────────


class InMemoryRateLimiter:
    """Simple token-bucket rate limiter keyed by user UID.

    Suitable for single-process deployments.  For multi-process /
    multi-node production deployments, swap in a Redis-backed
    implementation.
    """

    def __init__(self, max_rpm: int = 60) -> None:
        self._max_rpm = max_rpm
        self._window_seconds = 60.0
        self._requests: dict[str, list[float]] = defaultdict(list)

    async def check(self, key: str) -> bool:
        """Return ``True`` if the request is allowed, ``False`` if rate-
        limited.
        """
        now = time.monotonic()
        window_start = now - self._window_seconds

        # Prune expired entries.
        self._requests[key] = [
            ts for ts in self._requests[key] if ts > window_start
        ]

        if len(self._requests[key]) >= self._max_rpm:
            return False

        self._requests[key].append(now)
        return True


# Module-level singleton (overridden in tests).
_rate_limiter: InMemoryRateLimiter | None = None


def get_rate_limiter() -> InMemoryRateLimiter:
    """Return the module-level rate limiter singleton."""
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = InMemoryRateLimiter(
            max_rpm=get_settings().rate_limit_rpm,
        )
    return _rate_limiter


async def rate_limit(
    user: StaffUser = Depends(verify_firebase_token),
) -> StaffUser:
    """FastAPI dependency that enforces per-user rate limiting.

    Chains with ``verify_firebase_token`` so it receives the authenticated
    ``StaffUser`` via FastAPI's DI system.

    Raises:
        HTTPException 429: Rate limit exceeded.
    """
    limiter = get_rate_limiter()
    allowed = await limiter.check(user.uid)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Please try again later.",
        )
    return user


# ── LLM Factory ─────────────────────────────────────────────────────────


from functools import lru_cache

@lru_cache()
def get_llm() -> Any:
    """Create and return an instrumented ``ChatGoogleGenerativeAI`` instance.

    The model name, temperature, and API key are sourced from
    ``Settings``.  This function is designed to be overridden in tests
    via ``app.dependency_overrides[get_llm]``.
    """
    from langchain_google_genai import ChatGoogleGenerativeAI

    from app.utils.genai_telemetry import instrument_llm

    settings = get_settings()
    llm = ChatGoogleGenerativeAI(
        model=settings.llm_model_name,
        temperature=settings.llm_temperature,
        google_api_key=settings.google_api_key.get_secret_value(),
    )
    return instrument_llm(llm, model_name=settings.llm_model_name)


# ── Edge Telemetry Access ──────────────────────────────────────────────

# Populated by main.py lifespan.
_edge_consumer: EdgeStreamConsumer | None = None


def set_edge_consumer(consumer: EdgeStreamConsumer) -> None:
    """Store the active edge consumer reference (called by lifespan)."""
    global _edge_consumer
    _edge_consumer = consumer


def get_edge_consumer() -> EdgeStreamConsumer | None:
    """Return the active edge stream consumer, if started."""
    return _edge_consumer


async def get_edge_data() -> dict[str, Any]:
    """Return the latest filtered edge telemetry snapshot as a dict.

    If the edge consumer hasn't produced data yet, returns a placeholder.
    """
    consumer = get_edge_consumer()
    if consumer is None:
        return {"status": "edge_consumer_not_started"}

    snapshot = consumer.get_latest_snapshot()
    if snapshot is None:
        return {"status": "awaiting_first_telemetry"}

    return snapshot.model_dump(mode="json")
