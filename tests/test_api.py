"""
OmniCrew AI — FastAPI integration tests.

These tests use ``httpx.AsyncClient`` with an ASGI transport to exercise
the API endpoints end-to-end (with mocked LLM, edge consumer, and
Firebase auth).

Coverage:
* Health check
* Authenticated query (success + error cases)
* Rate limiting
* Invalid payloads (Pydantic validation)
* Telemetry endpoint (authorized + unauthorized)
* Multilingual round-trip (Spanish, French, Arabic)
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient


# ═══════════════════════════════════════════════════════════════════════
#  Health Check
# ═══════════════════════════════════════════════════════════════════════


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_ok(self, app_client: AsyncClient) -> None:
        resp = await app_client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ═══════════════════════════════════════════════════════════════════════
#  Query Endpoint — Success
# ═══════════════════════════════════════════════════════════════════════


class TestQuerySuccess:
    @pytest.mark.asyncio
    async def test_query_success(
        self,
        app_client: AsyncClient,
        valid_headers: dict[str, str],
    ) -> None:
        """Valid request → 200 with well-formed QueryResponse."""
        resp = await app_client.post(
            "/query",
            json={
                "query": "Gate C is flooded, where do I send the overflow?",
                "location": "Gate-C",
                "language": "en",
            },
            headers=valid_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "response" in body
        assert body["language"] == "en"
        assert "agent_used" in body
        assert "session_id" in body


# ═══════════════════════════════════════════════════════════════════════
#  Query Endpoint — Validation
# ═══════════════════════════════════════════════════════════════════════


class TestQueryValidation:
    @pytest.mark.asyncio
    async def test_query_invalid_payload_missing_fields(
        self,
        app_client: AsyncClient,
        valid_headers: dict[str, str],
    ) -> None:
        """Missing required fields → 422."""
        resp = await app_client.post(
            "/query",
            json={"query": "Hello"},
            headers=valid_headers,
        )
        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_query_invalid_language(
        self,
        app_client: AsyncClient,
        valid_headers: dict[str, str],
    ) -> None:
        """Invalid language code → 422."""
        resp = await app_client.post(
            "/query",
            json={
                "query": "Test query",
                "location": "Gate-A",
                "language": "xx",
            },
            headers=valid_headers,
        )
        assert resp.status_code == 422


# ═══════════════════════════════════════════════════════════════════════
#  Rate Limiting
# ═══════════════════════════════════════════════════════════════════════


class TestRateLimiting:
    @pytest.mark.asyncio
    async def test_query_rate_limited(self, app_client: AsyncClient) -> None:
        """Exceed rate limit → 429."""
        from app.dependencies import get_rate_limiter

        limiter = get_rate_limiter()
        original_max = limiter._max_rpm
        limiter._max_rpm = 2  # very low limit for testing

        headers = {"Authorization": "Bearer mock-test-token"}
        payload = {
            "query": "Test query",
            "location": "Gate-A",
        }

        results = []
        for _ in range(5):
            resp = await app_client.post(
                "/query", json=payload, headers=headers
            )
            results.append(resp.status_code)

        # At least one should be 429.
        assert 429 in results

        # Restore original limit.
        limiter._max_rpm = original_max


# ═══════════════════════════════════════════════════════════════════════
#  Telemetry Endpoint
# ═══════════════════════════════════════════════════════════════════════


class TestTelemetryEndpoint:
    @pytest.mark.asyncio
    async def test_telemetry_authorized(
        self,
        app_client: AsyncClient,
        command_center_headers: dict[str, str],
    ) -> None:
        """command-center role → 200 with telemetry data."""
        resp = await app_client.get("/telemetry", headers=command_center_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "gate_id" in body

    @pytest.mark.asyncio
    async def test_telemetry_unauthorized_role(
        self,
        app_client: AsyncClient,
    ) -> None:
        """Non-command-center role → 403."""
        # Create a client with medic role override
        from app.main import app
        from app.dependencies import verify_firebase_token
        from tests.conftest import _make_mock_auth

        app.dependency_overrides[verify_firebase_token] = _make_mock_auth("medic", "Gate-A")
        resp = await app_client.get(
            "/telemetry",
            headers={"Authorization": "Bearer mock-medic-token"},
        )
        assert resp.status_code == 403
        # Restore command-center override
        app.dependency_overrides[verify_firebase_token] = _make_mock_auth("command-center", "HQ")


# ═══════════════════════════════════════════════════════════════════════
#  Multilingual Round-Trip
# ═══════════════════════════════════════════════════════════════════════


class TestMultilingual:
    """Verify that non-English queries produce responses in the correct
    language.
    """

    @pytest_asyncio.fixture
    async def multilingual_client(
        self,
        multilingual_mock_llm: Any,
        sample_filtered_telemetry: Any,
    ):
        """Client with the multilingual mock LLM."""
        from app.main import app
        from app.dependencies import (
            get_llm,
            set_edge_consumer,
            verify_firebase_token,
        )
        from app.edge.stream import EdgeStreamConsumer
        from tests.conftest import _make_mock_auth

        mock_consumer = MagicMock(spec=EdgeStreamConsumer)
        mock_consumer.get_latest_snapshot.return_value = sample_filtered_telemetry
        set_edge_consumer(mock_consumer)

        app.dependency_overrides[verify_firebase_token] = _make_mock_auth("usher", "Gate-C")
        app.dependency_overrides[get_llm] = lambda: multilingual_mock_llm

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield client

        app.dependency_overrides.clear()

    @pytest.mark.asyncio
    async def test_multilingual_query_spanish(
        self, multilingual_client: AsyncClient
    ) -> None:
        """Spanish query → response in Spanish."""
        resp = await multilingual_client.post(
            "/query",
            json={
                "query": "La puerta C está inundada, ¿a dónde envío el desbordamiento?",
                "location": "Gate-C",
                "language": "es",
            },
            headers={"Authorization": "Bearer mock-usher-token"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["language"] == "es"
        assert "Redirigir" in body["response"] or "Puerta" in body["response"]

    @pytest.mark.asyncio
    async def test_multilingual_query_french(
        self, multilingual_client: AsyncClient
    ) -> None:
        """French query → response in French."""
        resp = await multilingual_client.post(
            "/query",
            json={
                "query": "La porte C est inondée, où rediriger le flux ?",
                "location": "Gate-C",
                "language": "fr",
            },
            headers={"Authorization": "Bearer mock-usher-token"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["language"] == "fr"
        assert "Rediriger" in body["response"] or "Porte" in body["response"]

    @pytest.mark.asyncio
    async def test_multilingual_query_arabic(
        self, multilingual_client: AsyncClient
    ) -> None:
        """Arabic query → response in Arabic."""
        resp = await multilingual_client.post(
            "/query",
            json={
                "query": "البوابة C مغمورة بالمياه، أين أوجه الفائض؟",
                "location": "Gate-C",
                "language": "ar",
            },
            headers={"Authorization": "Bearer mock-usher-token"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["language"] == "ar"
        assert any("\u0600" <= ch <= "\u06FF" for ch in body["response"])
