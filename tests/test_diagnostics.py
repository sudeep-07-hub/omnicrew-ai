import pytest
from httpx import AsyncClient

@pytest.mark.asyncio
async def test_genai_usage_unauthorized(app_client: AsyncClient):
    from app.main import app
    from app.dependencies import verify_firebase_token
    from tests.conftest import _make_mock_auth
    
    # Temporarily override with medic role
    app.dependency_overrides[verify_firebase_token] = _make_mock_auth("medic", "Gate-A")
    try:
        response = await app_client.get("/diagnostics/genai-usage")
        assert response.status_code == 403
    finally:
        # Restore command-center override for other tests
        app.dependency_overrides[verify_firebase_token] = _make_mock_auth("command-center", "HQ")

@pytest.mark.asyncio
async def test_genai_usage_authorized(app_client: AsyncClient, command_center_headers: dict[str, str]):
    response = await app_client.get(
        "/diagnostics/genai-usage",
        headers=command_center_headers
    )
    assert response.status_code == 200
    data = response.json()
    assert "call_count" in data
    assert "calls" in data
