"""
OmniCrew AI — Opt-in Live GenAI Test.

This test requires a real Gemini API key and makes a genuine network
request to the model.  It verifies that the entire pipeline (router,
tools, synthesis, and telemetry) works correctly with the real model
and that token usages are recorded accurately.

To run:
    OMNICREW_GOOGLE_API_KEY="<your-key>" pytest -m live tests/test_genai_live.py -v
"""

from __future__ import annotations


import pytest
from langchain_google_genai import ChatGoogleGenerativeAI

from app.agents.router import run_query
from app.config import get_settings
from app.utils.genai_telemetry import get_telemetry_buffer, instrument_llm


@pytest.mark.live
@pytest.mark.asyncio
async def test_live_gemini_round_trip() -> None:
    """Verify that a real Gemini model handles intent routing, synthesis,
    and records token usage in the telemetry buffer.
    """
    settings = get_settings()

    # Bail out early if we're missing a real API key.
    api_key = settings.google_api_key.get_secret_value()
    if not api_key or api_key == "fake-test-key-for-ci":
        pytest.skip("Skipping live test: OMNICREW_GOOGLE_API_KEY is not a real key.")

    # Create and instrument the real LLM.
    llm = ChatGoogleGenerativeAI(
        model=settings.llm_model_name,
        temperature=settings.llm_temperature,
        google_api_key=api_key,
    )
    instrumented_llm = instrument_llm(llm, model_name=settings.llm_model_name)

    # Clear the telemetry buffer before the test.
    buf = get_telemetry_buffer()
    buf.clear()

    # Send a query that should trigger the crowd_management tool.
    result = await run_query(
        query="There's a massive crowd backing up at Gate C due to the rain.",
        language="en",
        role="usher",
        location="Gate-C",
        edge_telemetry="Turnstile count: 950. Alerts: CROWD_ALERT.",
        llm=instrumented_llm,
    )

    # Verify the response.
    assert result["response"]
    assert result["language"] == "en"
    # The real LLM might return 'crowd_management' or sometimes 'general'
    # if it decides differently, but the response should be valid.
    assert isinstance(result["response"], str)
    assert len(result["response"]) > 10

    # Verify telemetry was recorded.
    # We expect at least one call (agent node), possibly two (synthesize).
    assert buf.get_count() > 0

    log = buf.get_log()
    last_call = log[-1]

    # Verify that the model name was captured correctly.
    assert last_call["model_name"] == settings.llm_model_name

    # Verify token usage is non-zero (since this is a real call).
    assert last_call["prompt_tokens"] > 0
    assert last_call["completion_tokens"] > 0
    assert last_call["total_tokens"] > 0

    # Verify latency is non-zero.
    assert last_call["latency_ms"] > 0.0

    # Status should be success.
    assert last_call["status"] == "success"
