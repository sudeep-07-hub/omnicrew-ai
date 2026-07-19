import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_root(app_client: AsyncClient):
    response = await app_client.get("/", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/docs"

@pytest.mark.asyncio
async def test_main_query_unauthorized(app_client: AsyncClient):
    app.dependency_overrides.clear()
    response = await app_client.post("/query", json={"query": "test"})
    assert response.status_code == 401

@pytest.mark.asyncio
async def test_lifespan_manually():
    import firebase_admin
    from app.main import lifespan
    from unittest.mock import patch, AsyncMock, MagicMock

    with patch("app.main.start_background_consumer") as mock_start:
        mock_consumer = MagicMock()
        mock_consumer.shutdown = AsyncMock()
        mock_start.return_value = mock_consumer
        
        # Save old apps so we don't break subsequent tests
        old_apps = firebase_admin._apps.copy()
        firebase_admin._apps.clear()
        
        try:
            async with lifespan(app):
                pass
            mock_start.assert_called_once()
            mock_consumer.shutdown.assert_called_once()
        finally:
            firebase_admin._apps = old_apps
