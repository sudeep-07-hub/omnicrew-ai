"""
OmniCrew AI — Mocked async IoT telemetry stream consumer.

In production this module would connect to a real message broker (Kafka,
Pub/Sub, MQTT) to ingest high-throughput sensor data from stadium edge
nodes.  For this deliverable it generates **synthetic but realistic**
telemetry at configurable intervals, runs each event through the edge
``TelemetryFilter``, and maintains an in-memory snapshot of the latest
reading for API consumption.

Architecture note:
    ``agents/`` never imports this module directly — it accesses filtered
    telemetry exclusively through the ``get_edge_data`` dependency in
    ``app.dependencies``.
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncGenerator
from datetime import datetime, timezone

from app.config import Settings, get_settings
from app.edge.filter import (
    FilteredTelemetry,
    RawTelemetry,
    TelemetryFilter,
)

logger = logging.getLogger(__name__)

# ── Synthetic Data Generation ────────────────────────────────────────────

_GATE_IDS: list[str] = [
    "Gate-A",
    "Gate-B",
    "Gate-C",
    "Gate-D",
    "Gate-E",
    "Gate-F",
]

# Sample staff notes — some contain PII intentionally for scrubbing tests.
_SAMPLE_NOTES: list[str] = [
    "All clear at this gate.",
    "John Michael Smith reported a spill near turnstile 3.",
    "Contact medical at +1-555-987-6543 for update.",
    "VIP credential issue — refer to security lead.",
    "Fan with email ticket john.doe@fifa.org needs re-entry.",
    "Temperature feels high, fans requesting water.",
    "",
    "Heavy foot traffic, recommend overflow routing.",
]


def _generate_raw_telemetry() -> RawTelemetry:
    """Produce a single synthetic telemetry event with realistic ranges."""
    return RawTelemetry(
        gate_id=random.choice(_GATE_IDS),
        turnstile_count=random.randint(200, 1200),
        crowd_density=round(random.uniform(0.2, 0.98), 2),
        temperature_c=round(random.uniform(28.0, 48.0), 1),
        humidity_pct=round(random.uniform(30.0, 90.0), 1),
        notes=random.choice(_SAMPLE_NOTES),
        timestamp=datetime.now(timezone.utc),
    )


# ── Stream Consumer ─────────────────────────────────────────────────────


class EdgeStreamConsumer:
    """Async consumer that yields filtered telemetry at fixed intervals.

    Usage::

        consumer = EdgeStreamConsumer(settings)
        async for event in consumer.consume():
            print(event)
    """

    def __init__(
        self,
        settings: Settings | None = None,
        *,
        interval_seconds: float = 5.0,
    ) -> None:
        self._settings = settings or get_settings()
        self._interval = interval_seconds
        self._filter = TelemetryFilter(self._settings)
        self._latest: FilteredTelemetry | None = None
        self._running = False
        self._task: asyncio.Task[None] | None = None

    # ── Public API ───────────────────────────────────────────────────

    async def consume(self) -> AsyncGenerator[FilteredTelemetry, None]:
        """Yield filtered telemetry events at ``interval_seconds`` cadence.

        Each raw event is generated synthetically, passed through the
        ``TelemetryFilter``, and then yielded.  The latest event is also
        cached in ``_latest`` for snapshot access.
        """
        self._running = True
        try:
            while self._running:
                raw = _generate_raw_telemetry()
                filtered = self._filter.filter_telemetry(raw)
                self._latest = filtered
                yield filtered
                await asyncio.sleep(self._interval)
        finally:
            self._running = False

    def get_latest_snapshot(self) -> FilteredTelemetry | None:
        """Return the most recently consumed telemetry event, or ``None``
        if the consumer hasn't started yet.
        """
        return self._latest

    def stop(self) -> None:
        """Signal the consumer loop to stop after the current iteration."""
        self._running = False

    # ── Background Task Lifecycle ────────────────────────────────────

    async def _background_loop(self) -> None:
        """Internal loop used when the consumer runs as a background task."""
        async for _event in self.consume():
            # Events are cached in self._latest automatically.
            if not self._running:
                break

    def start_background(self) -> asyncio.Task[None]:
        """Launch the consumer as a background ``asyncio.Task``.

        Returns the task handle so callers can cancel it during shutdown.
        """
        self._task = asyncio.create_task(
            self._background_loop(),
            name="edge-stream-consumer",
        )
        logger.info("Edge stream consumer started (interval=%.1fs).", self._interval)
        return self._task

    async def shutdown(self) -> None:
        """Gracefully stop the background consumer."""
        self.stop()
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            logger.info("Edge stream consumer shut down.")


async def start_background_consumer(
    settings: Settings | None = None,
) -> EdgeStreamConsumer:
    """Factory: create an ``EdgeStreamConsumer`` and launch it in the
    background.  Called from ``main.py`` lifespan.
    """
    consumer = EdgeStreamConsumer(settings)
    consumer.start_background()
    return consumer
