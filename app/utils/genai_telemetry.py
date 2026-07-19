"""
OmniCrew AI — GenAI Call Telemetry.

Thin instrumentation layer that wraps every LLM call.  For each
invocation it records: timestamp, model name, prompt/completion tokens,
latency (ms), and which agent or tool triggered the call.

The last N records are held in an in-memory ring buffer — this is
evidence for hackathon judges, not a production analytics pipeline.

Architecture:
    ``dependencies.get_llm()`` returns an ``InstrumentedChatModel``
    instead of a bare ``ChatGoogleGenerativeAI``.  The rest of the
    codebase (router, tools) is unaware of the instrumentation.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


# ═══════════════════════════════════════════════════════════════════════
#  Call Record Schema
# ═══════════════════════════════════════════════════════════════════════


class GenAICallRecord(BaseModel):
    """Schema for a single recorded LLM invocation."""

    timestamp: str = Field(
        ...,
        description="ISO-8601 UTC timestamp of the call.",
    )
    model_name: str = Field(
        ...,
        max_length=128,
        description="Name of the Gemini model used.",
    )
    prompt_tokens: int = Field(
        default=0,
        ge=0,
        description="Number of input (prompt) tokens.",
    )
    completion_tokens: int = Field(
        default=0,
        ge=0,
        description="Number of output (completion) tokens.",
    )
    total_tokens: int = Field(
        default=0,
        ge=0,
        description="Total tokens consumed (prompt + completion).",
    )
    latency_ms: float = Field(
        default=0.0,
        ge=0.0,
        description="Wall-clock latency of the LLM call in milliseconds.",
    )
    triggered_by: str = Field(
        default="router",
        max_length=128,
        description="Which agent, tool, or graph node triggered this call.",
    )
    status: str = Field(
        default="success",
        description="Call outcome: 'success' or 'error'.",
    )


# ═══════════════════════════════════════════════════════════════════════
#  Ring Buffer
# ═══════════════════════════════════════════════════════════════════════


class GenAITelemetryBuffer:
    """Thread-safe ring buffer that holds the last *max_size* call records.

    Usage::

        buf = GenAITelemetryBuffer(max_size=50)
        buf.record(GenAICallRecord(...))
        log = buf.get_log()
    """

    def __init__(self, max_size: int = 50) -> None:
        self._buffer: deque[GenAICallRecord] = deque(maxlen=max_size)
        self._lock = threading.Lock()

    def record(self, entry: GenAICallRecord) -> None:
        """Append a call record to the buffer (thread-safe)."""
        with self._lock:
            self._buffer.append(entry)

    def get_log(self) -> list[dict[str, Any]]:
        """Return all buffered records as a list of dicts (newest last)."""
        with self._lock:
            return [r.model_dump() for r in self._buffer]

    def get_count(self) -> int:
        """Return the number of recorded calls."""
        with self._lock:
            return len(self._buffer)

    def clear(self) -> None:
        """Clear all records."""
        with self._lock:
            self._buffer.clear()


# Module-level singleton.
_global_buffer = GenAITelemetryBuffer(max_size=50)


def get_telemetry_buffer() -> GenAITelemetryBuffer:
    """Return the global telemetry buffer singleton."""
    return _global_buffer


# ═══════════════════════════════════════════════════════════════════════
#  Instrumented Chat Model Proxy
# ═══════════════════════════════════════════════════════════════════════


def _extract_usage(response: Any) -> dict[str, int]:
    """Extract token-usage metadata from a LangChain AIMessage.

    ``langchain-google-genai`` attaches ``usage_metadata`` to responses
    with keys ``input_tokens``, ``output_tokens``, ``total_tokens``.
    If the metadata is missing (e.g. in mocks), returns zeros.
    """
    usage = getattr(response, "usage_metadata", None)
    if usage and isinstance(usage, dict):
        return {
            "prompt_tokens": usage.get("input_tokens", 0) or 0,
            "completion_tokens": usage.get("output_tokens", 0) or 0,
            "total_tokens": usage.get("total_tokens", 0) or 0,
        }
    return {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}


class InstrumentedChatModel:
    """Transparent proxy that wraps a LangChain chat model and records
    telemetry for every ``invoke()`` / ``ainvoke()`` call.

    All attribute access is forwarded to the underlying model, so this
    proxy is invisible to callers.

    Usage::

        llm = ChatGoogleGenerativeAI(...)
        instrumented = InstrumentedChatModel(llm, model_name="gemini-2.0-flash")
        # Use ``instrumented`` exactly like ``llm``.
    """

    def __init__(
        self,
        llm: Any,
        *,
        model_name: str = "unknown",
        triggered_by: str = "router",
        buffer: GenAITelemetryBuffer | None = None,
    ) -> None:
        # Store on the instance dict directly to avoid __setattr__ loops.
        object.__setattr__(self, "_llm", llm)
        object.__setattr__(self, "_model_name", model_name)
        object.__setattr__(self, "_triggered_by", triggered_by)
        object.__setattr__(self, "_buffer", buffer or get_telemetry_buffer())

    # ── Proxied Attribute Access ─────────────────────────────────────

    def __getattr__(self, name: str) -> Any:
        """Forward all attribute access to the wrapped LLM."""
        return getattr(object.__getattribute__(self, "_llm"), name)

    # ── Tool Binding ─────────────────────────────────────────────────

    def bind_tools(self, tools: list[Any], **kwargs: Any) -> "InstrumentedChatModel":
        """Bind tools on the underlying LLM and return a new instrumented wrapper."""
        llm = object.__getattribute__(self, "_llm")
        bound = llm.bind_tools(tools, **kwargs)
        return InstrumentedChatModel(
            bound,
            model_name=object.__getattribute__(self, "_model_name"),
            triggered_by=object.__getattribute__(self, "_triggered_by"),
            buffer=object.__getattribute__(self, "_buffer"),
        )

    # ── Synchronous Invocation ───────────────────────────────────────

    def invoke(self, messages: Any, **kwargs: Any) -> Any:
        """Invoke the LLM synchronously and record telemetry."""
        llm = object.__getattribute__(self, "_llm")
        buf = object.__getattribute__(self, "_buffer")
        model_name = object.__getattribute__(self, "_model_name")
        triggered_by = object.__getattribute__(self, "_triggered_by")

        start = time.perf_counter()
        status = "success"
        response = None
        try:
            response = llm.invoke(messages, **kwargs)
            return response
        except Exception:
            status = "error"
            raise
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            usage = _extract_usage(response) if response else {}
            record = GenAICallRecord(
                timestamp=datetime.now(timezone.utc).isoformat(),
                model_name=model_name,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                latency_ms=round(latency_ms, 2),
                triggered_by=triggered_by,
                status=status,
            )
            buf.record(record)

    # ── Async Invocation ─────────────────────────────────────────────

    async def ainvoke(self, messages: Any, **kwargs: Any) -> Any:
        """Invoke the LLM asynchronously and record telemetry."""
        llm = object.__getattribute__(self, "_llm")
        buf = object.__getattribute__(self, "_buffer")
        model_name = object.__getattribute__(self, "_model_name")
        triggered_by = object.__getattribute__(self, "_triggered_by")

        start = time.perf_counter()
        status = "success"
        response = None
        try:
            # If underlying LLM supports ainvoke, use it; else fall back.
            if hasattr(llm, "ainvoke"):
                response = await llm.ainvoke(messages, **kwargs)
            else:
                response = llm.invoke(messages, **kwargs)
            return response
        except Exception:
            status = "error"
            raise
        finally:
            latency_ms = (time.perf_counter() - start) * 1000
            usage = _extract_usage(response) if response else {}
            record = GenAICallRecord(
                timestamp=datetime.now(timezone.utc).isoformat(),
                model_name=model_name,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                latency_ms=round(latency_ms, 2),
                triggered_by=triggered_by,
                status=status,
            )
            buf.record(record)


def instrument_llm(
    llm: Any,
    *,
    model_name: str = "unknown",
    triggered_by: str = "router",
) -> InstrumentedChatModel:
    """Factory: wrap an LLM with ``InstrumentedChatModel``.

    Args:
        llm: A LangChain chat model instance.
        model_name: The model name to record in telemetry.
        triggered_by: Default trigger label.

    Returns:
        An ``InstrumentedChatModel`` wrapping *llm*.
    """
    return InstrumentedChatModel(
        llm,
        model_name=model_name,
        triggered_by=triggered_by,
    )
