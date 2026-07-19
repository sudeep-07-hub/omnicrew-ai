import pytest
import asyncio
from unittest.mock import MagicMock
from app.utils.genai_telemetry import (
    GenAITelemetryBuffer,
    GenAICallRecord,
    InstrumentedChatModel,
    instrument_llm,
    _extract_usage
)

def test_buffer_operations():
    buf = GenAITelemetryBuffer(max_size=2)
    assert buf.get_count() == 0
    
    record1 = GenAICallRecord(timestamp="2026-01-01T00:00:00Z", model_name="test1")
    record2 = GenAICallRecord(timestamp="2026-01-01T00:01:00Z", model_name="test2")
    record3 = GenAICallRecord(timestamp="2026-01-01T00:02:00Z", model_name="test3")
    
    buf.record(record1)
    buf.record(record2)
    assert buf.get_count() == 2
    
    # Test ring buffer eviction
    buf.record(record3)
    assert buf.get_count() == 2
    log = buf.get_log()
    assert log[0]["model_name"] == "test2"
    assert log[1]["model_name"] == "test3"
    
    buf.clear()
    assert buf.get_count() == 0

def test_extract_usage():
    class MockResponse:
        usage_metadata = {"input_tokens": 10, "output_tokens": 20, "total_tokens": 30}
    
    usage = _extract_usage(MockResponse())
    assert usage["prompt_tokens"] == 10
    assert usage["completion_tokens"] == 20
    assert usage["total_tokens"] == 30
    
    assert _extract_usage(None) == {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}

def test_instrumented_chat_model_sync():
    mock_llm = MagicMock()
    mock_llm.invoke.return_value = "response"
    
    buf = GenAITelemetryBuffer()
    instrumented = InstrumentedChatModel(mock_llm, model_name="test-model", buffer=buf)
    
    assert instrumented.invoke("hello") == "response"
    assert buf.get_count() == 1
    assert buf.get_log()[0]["model_name"] == "test-model"

@pytest.mark.asyncio
async def test_instrumented_chat_model_async():
    mock_llm = MagicMock()
    async def async_invoke(*args, **kwargs):
        return "async_response"
    mock_llm.ainvoke = async_invoke
    
    buf = GenAITelemetryBuffer()
    instrumented = InstrumentedChatModel(mock_llm, model_name="test-model", buffer=buf)
    
    assert await instrumented.ainvoke("hello") == "async_response"
    assert buf.get_count() == 1
    assert buf.get_log()[0]["status"] == "success"

def test_bind_tools():
    mock_llm = MagicMock()
    mock_bound = MagicMock()
    mock_llm.bind_tools.return_value = mock_bound
    
    instrumented = instrument_llm(mock_llm, model_name="test-model")
    bound_instrumented = instrumented.bind_tools(["tool1"])
    
    # We should get a new InstrumentedChatModel
    assert isinstance(bound_instrumented, InstrumentedChatModel)
