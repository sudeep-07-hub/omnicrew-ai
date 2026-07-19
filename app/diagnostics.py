"""
OmniCrew AI — Diagnostics endpoints.

Exposes ``GET /diagnostics/genai-usage`` so that a judge, teammate, or
automated script can verify the live deployment is genuinely calling a
GenAI model (not returning canned strings).

The endpoint is auth-protected at the ``command-center`` scope — only
operators with elevated credentials can view the call log.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.dependencies import StaffUser, verify_firebase_token
from app.utils.genai_telemetry import get_telemetry_buffer

# ═══════════════════════════════════════════════════════════════════════
#  Router
# ═══════════════════════════════════════════════════════════════════════

diagnostics_router = APIRouter(
    prefix="/diagnostics",
    tags=["diagnostics"],
)


# ═══════════════════════════════════════════════════════════════════════
#  Response Schema
# ═══════════════════════════════════════════════════════════════════════


class GenAIUsageResponse(BaseModel):
    """Response schema for the GenAI usage diagnostics endpoint."""

    call_count: int = Field(
        ...,
        ge=0,
        description="Total number of GenAI calls recorded in the buffer.",
    )
    calls: list[dict[str, Any]] = Field(
        ...,
        description=(
            "List of recorded GenAI call records (newest last). "
            "Each entry includes: timestamp, model_name, prompt_tokens, "
            "completion_tokens, total_tokens, latency_ms, triggered_by, status."
        ),
    )


# ═══════════════════════════════════════════════════════════════════════
#  Endpoint
# ═══════════════════════════════════════════════════════════════════════


@diagnostics_router.get(
    "/genai-usage",
    response_model=GenAIUsageResponse,
    summary="GenAI Call Log",
    description=(
        "Returns the last N GenAI (Gemini) calls made by the system, "
        "including model names, token counts, latency, and timestamps. "
        "This is the proof artifact for verifying live GenAI usage."
    ),
)
async def genai_usage(
    user: StaffUser = Depends(verify_firebase_token),
) -> GenAIUsageResponse:
    """Return the GenAI call telemetry log.

    Restricted to ``command-center`` role.

    Raises:
        HTTPException 403: If the caller's role is not command-center.
    """
    if user.role != "command-center":
        raise HTTPException(
            status_code=403,
            detail="GenAI diagnostics restricted to command-center role.",
        )

    buf = get_telemetry_buffer()
    return GenAIUsageResponse(
        call_count=buf.get_count(),
        calls=buf.get_log(),
    )
