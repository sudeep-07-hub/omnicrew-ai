"""
OmniCrew AI — Shared pytest fixtures.

All fixtures are hermetic: no real LLM calls, no real IoT streams,
no real Firebase Auth.  The Firebase token verifier is overridden with
a dependency that returns a deterministic ``StaffUser``.
"""

from __future__ import annotations

import os
from typing import Any
from unittest.mock import MagicMock
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage

from app.config import Settings
from app.edge.filter import FilteredTelemetry, RawTelemetry

# ── Environment Setup ───────────────────────────────────────────────────
# Set env vars BEFORE importing the app so that ``Settings`` picks them up.

os.environ.setdefault("OMNICREW_GOOGLE_API_KEY", "fake-test-key-for-ci")
os.environ.setdefault("OMNICREW_EDGE_CROWD_THRESHOLD", "500")
os.environ.setdefault("OMNICREW_EDGE_TEMPERATURE_MAX_C", "40.0")
os.environ.setdefault("OMNICREW_RATE_LIMIT_RPM", "1000")
os.environ.setdefault("OMNICREW_FIREBASE_PROJECT_ID", "test-project")


# ── Settings Fixture ────────────────────────────────────────────────────


@pytest.fixture
def settings() -> Settings:
    """Return a ``Settings`` instance with test-safe defaults."""
    return Settings(
        google_api_key="fake-test-key-for-ci",  # type: ignore[arg-type]
        firebase_project_id="test-project",
        edge_crowd_threshold=500,
        edge_temperature_max_c=40.0,
        rate_limit_rpm=1000,
        hmac_secret="test-hmac-secret-key",
    )


# ── Mock LLM ────────────────────────────────────────────────────────────


class MockChatModel:
    """Deterministic mock LLM that returns pre-configured responses.

    Supports ``.bind_tools()`` (returns self), ``.invoke()`` and
    ``.ainvoke()`` for synchronous and async graph execution.
    """

    def __init__(self, response: AIMessage | None = None) -> None:
        self._response = response or AIMessage(
            content="Test response from OmniCrew AI."
        )

    def bind_tools(self, tools: list[Any]) -> "MockChatModel":
        """No-op tool binding — returns self."""
        return self

    def invoke(self, messages: Any, **kwargs: Any) -> AIMessage:
        return self._response

    async def ainvoke(self, messages: Any, **kwargs: Any) -> AIMessage:
        return self._response


@pytest.fixture
def mock_llm() -> MockChatModel:
    """A mock LLM that returns a simple text response (no tool calls)."""
    return MockChatModel()


@pytest.fixture
def mock_llm_with_crowd_tool() -> MockChatModel:
    """A mock LLM that returns a ``crowd_management`` tool call."""
    return MockChatModel(
        response=AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_001",
                    "name": "crowd_management",
                    "args": {
                        "gate": "Gate-C",
                        "issue": "overflow due to flooding",
                        "current_count": 950,
                    },
                }
            ],
        )
    )


@pytest.fixture
def mock_llm_with_medical_tool() -> MockChatModel:
    """A mock LLM that returns a ``medical_assistance`` tool call."""
    return MockChatModel(
        response=AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_002",
                    "name": "medical_assistance",
                    "args": {
                        "location": "Section 200, Row A",
                        "issue_type": "heat exhaustion",
                        "severity": "moderate",
                        "patient_count": 2,
                    },
                }
            ],
        )
    )


@pytest.fixture
def mock_llm_with_access_tool() -> MockChatModel:
    """A mock LLM that returns an ``access_control`` tool call."""
    return MockChatModel(
        response=AIMessage(
            content="",
            tool_calls=[
                {
                    "id": "call_003",
                    "name": "access_control",
                    "args": {
                        "zone": "VIP Lounge East",
                        "issue": "credential denied at scanner",
                        "credential_type": "RFID badge",
                    },
                }
            ],
        )
    )


# ── Multilingual Mock LLM ──────────────────────────────────────────────


class MultilingualMockChatModel:
    """Mock LLM that detects language from messages and responds accordingly."""

    _RESPONSES: dict[str, str] = {
        "es": "Redirigir el tráfico de la Puerta C a las Puertas B y D.",
        "fr": "Rediriger le trafic de la Porte C vers les Portes B et D.",
        "ar": "أعد توجيه حركة المرور من البوابة C إلى البوابتين B و D.",
        "en": "Redirect traffic from Gate C to Gates B and D.",
    }

    def __init__(self) -> None:
        self._call_count = 0

    def bind_tools(self, tools: list[Any]) -> "MultilingualMockChatModel":
        return self

    def invoke(self, messages: Any, **kwargs: Any) -> AIMessage:
        self._call_count += 1
        if self._call_count == 1:
            return AIMessage(
                content="",
                tool_calls=[
                    {
                        "id": "call_ml",
                        "name": "crowd_management",
                        "args": {
                            "gate": "Gate-C",
                            "issue": "overflow",
                            "current_count": 900,
                        },
                    }
                ],
            )
        lang = "en"
        for msg in (messages if isinstance(messages, list) else [messages]):
            content = str(getattr(msg, "content", msg))
            for code in ("Spanish", "French", "Arabic"):
                if code in content:
                    lang = {"Spanish": "es", "French": "fr", "Arabic": "ar"}[code]
                    break
        return AIMessage(content=self._RESPONSES.get(lang, self._RESPONSES["en"]))

    async def ainvoke(self, messages: Any, **kwargs: Any) -> AIMessage:
        return self.invoke(messages, **kwargs)


@pytest.fixture
def multilingual_mock_llm() -> MultilingualMockChatModel:
    return MultilingualMockChatModel()


# ── Sample Telemetry ────────────────────────────────────────────────────


@pytest.fixture
def sample_raw_telemetry() -> RawTelemetry:
    """Raw telemetry with PII in the notes field."""
    return RawTelemetry(
        gate_id="Gate-C",
        turnstile_count=950,
        crowd_density=0.88,
        temperature_c=44.5,
        humidity_pct=65.0,
        notes="John Michael Smith called +1-555-123-4567 about email john.doe@fifa.org",
        timestamp=datetime(2026, 7, 15, 14, 30, 0, tzinfo=timezone.utc),
    )


@pytest.fixture
def sample_filtered_telemetry() -> FilteredTelemetry:
    """Pre-filtered telemetry (PII already scrubbed)."""
    return FilteredTelemetry(
        gate_id="Gate-C",
        turnstile_count=950,
        crowd_density=0.88,
        temperature_c=44.5,
        humidity_pct=65.0,
        notes="[NAME_REDACTED] called [PHONE_REDACTED] about email [EMAIL_REDACTED]",
        timestamp=datetime(2026, 7, 15, 14, 30, 0, tzinfo=timezone.utc),
        alerts=[
            "CROWD_ALERT: Gate-C turnstile count (950) exceeds threshold (500).",
            "DENSITY_ALERT: Gate-C crowd density (88%) exceeds 85%.",
            "HEAT_ALERT: Gate-C temperature (44.5°C) exceeds (40.0°C).",
        ],
    )


# ── Auth Helpers ────────────────────────────────────────────────────────

from app.dependencies import StaffUser, verify_firebase_token


def _make_mock_auth(role: str = "medic", gate: str = "Gate-A"):
    """Return a dependency override that returns a fake StaffUser."""
    async def _override():
        return StaffUser(
            uid="test-uid-001",
            email=f"test-{role}@omnicrew.test",
            role=role,
            gate=gate,
        )
    return _override


@pytest.fixture
def valid_headers() -> dict[str, str]:
    """Auth header — the token value doesn't matter because the
    dependency is overridden in app_client."""
    return {"Authorization": "Bearer mock-test-token"}


@pytest.fixture
def command_center_headers() -> dict[str, str]:
    return {"Authorization": "Bearer mock-cmdctr-token"}


# ── Async App Client ───────────────────────────────────────────────────


@pytest_asyncio.fixture
async def app_client(
    mock_llm: MockChatModel,
    sample_filtered_telemetry: FilteredTelemetry,
):
    """``httpx.AsyncClient`` wired to the FastAPI app with all external
    dependencies mocked out.
    """
    from app.main import app
    from app.dependencies import (
        get_llm,
        set_edge_consumer,
        verify_firebase_token,
    )
    from app.edge.stream import EdgeStreamConsumer

    # Mock edge consumer that returns our fixture data.
    mock_consumer = MagicMock(spec=EdgeStreamConsumer)
    mock_consumer.get_latest_snapshot.return_value = sample_filtered_telemetry
    set_edge_consumer(mock_consumer)

    # Override auth + LLM dependencies.
    app.dependency_overrides[verify_firebase_token] = _make_mock_auth("command-center", "HQ")
    app.dependency_overrides[get_llm] = lambda: mock_llm

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client

    # Cleanup overrides.
    app.dependency_overrides.clear()
