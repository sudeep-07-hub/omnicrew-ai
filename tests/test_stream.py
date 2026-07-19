import pytest
import asyncio
from app.edge.stream import EdgeStreamConsumer, start_background_consumer
from app.config import Settings
from unittest.mock import patch, AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_stream_consumer_background():
    # Provide a minimal mock consumer generator
    async def mock_consume():
        yield MagicMock()
        await asyncio.sleep(0.01)
        yield MagicMock()
        
    consumer = EdgeStreamConsumer(Settings(edge_api_url="http://test"))
    consumer.consume = mock_consume

    task = consumer.start_background()
    assert task is not None
    assert consumer._task is task
    
    await asyncio.sleep(0.05)
    
    await consumer.shutdown()
    assert task.cancelled() or task.done()
    
@pytest.mark.asyncio
@patch("app.edge.stream.EdgeStreamConsumer")
async def test_start_background_consumer(mock_consumer_class):
    mock_instance = mock_consumer_class.return_value
    consumer = await start_background_consumer(Settings(edge_api_url="http://test"))
    
    assert consumer is mock_instance
    mock_instance.start_background.assert_called_once()
