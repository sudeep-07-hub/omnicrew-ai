"""
OmniCrew AI — FastAPI application entrypoint.

Registers routes, middleware, and the lifespan hook that starts the
background edge-stream consumer and initializes Firebase Admin SDK.

All network-bound endpoints are ``async def`` to satisfy the project's
operational-efficiency requirement.
"""

from __future__ import annotations

import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import firebase_admin
from firebase_admin import credentials
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.agents.router import run_query
from app.config import get_settings
from app.diagnostics import diagnostics_router
from app.dependencies import (
    StaffUser,
    get_edge_data,
    get_llm,
    rate_limit,
    set_edge_consumer,
    verify_firebase_token,
)
from app.edge.filter import TelemetryFilter
from app.edge.stream import start_background_consumer

logger = logging.getLogger(__name__)

# ── Request / Response Schemas ──────────────────────────────────────────


class QueryRequest(BaseModel):
    """Incoming staff query payload."""

    query: str = Field(
        ...,
        min_length=1,
        max_length=2000,
        description="Natural-language query from the ground-staff member.",
    )
    language: str = Field(
        default="en",
        pattern=r"^(en|es|fr|ar)$",
        description="ISO language code for the response (en, es, fr, ar).",
    )
    location: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Staff member's current location (e.g. 'Gate-C', 'Section 204').",
    )
    session_id: str = Field(
        default_factory=lambda: str(uuid4()),
        max_length=64,
        description="Session identifier for conversation continuity.",
    )


class QueryResponse(BaseModel):
    """Response returned to the ground-staff member."""

    response: str = Field(
        ...,
        description="Localized, actionable instructions.",
    )
    language: str = Field(
        ...,
        description="Language of the response.",
    )
    agent_used: str = Field(
        ...,
        description="Which sub-agent handled the query (crowd_management, medical_assistance, access_control, or general).",
    )
    confidence: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Confidence score (1.0 for deterministic stubs).",
    )
    session_id: str = Field(
        ...,
        description="Echo of the session identifier.",
    )
    telemetry_snapshot: dict[str, Any] | None = Field(
        default=None,
        description="Latest edge telemetry snapshot (included for command-center role).",
    )


class HealthResponse(BaseModel):
    """Health-check response."""

    status: str = Field(default="ok", description="Service health status.")


# ── Lifespan ────────────────────────────────────────────────────────────


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: initialize Firebase Admin SDK, launch edge stream consumer.
    Shutdown: stop the consumer.
    """
    # Initialize Firebase Admin SDK with explicit credentials for local dev.
    # On GCP infrastructure (Cloud Run / Cloud Functions), ADC works automatically.
    # Locally, we need the service account key file.
    if not firebase_admin._apps:
        cred = None
        # 1. Check GOOGLE_APPLICATION_CREDENTIALS env var
        sa_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        if sa_path and Path(sa_path).is_file():
            cred = credentials.Certificate(sa_path)
            logger.info("Firebase Admin SDK: using GOOGLE_APPLICATION_CREDENTIALS=%s", sa_path)
        else:
            # 2. Check for sa-key.json in the project root
            local_key = Path(__file__).resolve().parent.parent / "sa-key.json"
            if local_key.is_file():
                cred = credentials.Certificate(str(local_key))
                logger.info("Firebase Admin SDK: using %s", local_key)
            else:
                logger.info("Firebase Admin SDK: using Application Default Credentials")

        firebase_admin.initialize_app(cred)
        logger.info("Firebase Admin SDK initialized.")

    settings = get_settings()
    consumer = await start_background_consumer(settings)
    set_edge_consumer(consumer)
    logger.info("OmniCrew AI started — edge consumer active.")
    yield
    await consumer.shutdown()
    logger.info("OmniCrew AI shut down.")


# ── App Instance ────────────────────────────────────────────────────────

app = FastAPI(
    title="OmniCrew AI",
    description=(
        "GenAI-powered decision-support co-pilot for stadium ground staff."
    ),
    version="2.0.0",
    lifespan=lifespan,
)

app.include_router(diagnostics_router)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Middleware ──────────────────────────────────────────────────────────


@app.middleware("http")
async def request_timing_middleware(request: Request, call_next) -> Response:
    """Log the wall-clock duration of every request."""
    start = time.perf_counter()
    response: Response = await call_next(request)
    duration_ms = (time.perf_counter() - start) * 1000
    response.headers["X-Process-Time-Ms"] = f"{duration_ms:.1f}"
    logger.debug(
        "%s %s → %s (%.1f ms)",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response


# ── Routes ──────────────────────────────────────────────────────────────


@app.get("/health", response_model=HealthResponse, tags=["ops"])
async def health() -> HealthResponse:
    """Lightweight health check — no auth required."""
    return HealthResponse()


@app.post("/query", response_model=QueryResponse, tags=["core"])
async def query_endpoint(
    request_data: QueryRequest,
    user: StaffUser = Depends(rate_limit),
    llm: Any = Depends(get_llm),
) -> QueryResponse:
    """Main query endpoint.

    Accepts a natural-language query from ground staff, fuses it with
    live edge telemetry, routes it through the LangGraph intent router,
    and returns a localized, actionable response. The user's role is
    derived from their Firebase authentication token, not the request body.
    """
    # Fetch edge telemetry context.
    edge_snapshot = await get_edge_data()
    edge_context = ""
    if "status" not in edge_snapshot:
        from app.edge.filter import FilteredTelemetry
        telemetry = FilteredTelemetry(**edge_snapshot)
        edge_context = TelemetryFilter.compress_context(telemetry)

    # Run through the LangGraph router.
    result = await run_query(
        query=request_data.query,
        language=request_data.language,
        role=user.role,
        location=request_data.location,
        edge_telemetry=edge_context,
        llm=llm,
    )

    # Include telemetry snapshot for command-center users.
    telem_out = edge_snapshot if user.role == "command-center" else None

    return QueryResponse(
        response=result["response"],
        language=result["language"],
        agent_used=result["agent_used"],
        confidence=1.0,
        session_id=request_data.session_id,
        telemetry_snapshot=telem_out,
    )


@app.get("/telemetry", tags=["ops"])
async def telemetry_endpoint(
    user: StaffUser = Depends(verify_firebase_token),
) -> dict[str, Any]:
    """Return the latest edge telemetry snapshot.

    Restricted to ``command-center`` role.
    """
    if user.role != "command-center":
        raise HTTPException(
            status_code=403,
            detail="Telemetry access restricted to command-center role.",
        )
    return await get_edge_data()


# ── Uvicorn Entry Point ────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=True,
    )
