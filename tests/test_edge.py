"""
OmniCrew AI — Edge filtering & PII masking unit tests.

These tests verify that:
* Individual PII categories are correctly redacted.
* Combined PII in a single string is fully scrubbed.
* Clean input passes through unchanged.
* Threshold evaluation produces the correct alerts.
* The context compressor respects token budgets.
* The stream consumer yields ``FilteredTelemetry`` (not raw).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.config import Settings
from app.edge.filter import (
    FilteredTelemetry,
    RawTelemetry,
    TelemetryFilter,
    scrub_pii,
)
from app.edge.stream import EdgeStreamConsumer


# ═══════════════════════════════════════════════════════════════════════
#  PII Scrubbing
# ═══════════════════════════════════════════════════════════════════════


class TestScrubPII:
    """Unit tests for ``scrub_pii()``."""

    def test_scrub_phone_number(self) -> None:
        """Phone numbers in international format are redacted."""
        text = "Call me at +1-555-123-4567 for details."
        result = scrub_pii(text)
        assert "+1-555-123-4567" not in result
        assert "[PHONE_REDACTED]" in result

    def test_scrub_email(self) -> None:
        """Email addresses are redacted."""
        text = "Send the report to john.doe@fifa.org please."
        result = scrub_pii(text)
        assert "john.doe@fifa.org" not in result
        assert "[EMAIL_REDACTED]" in result

    def test_scrub_name(self) -> None:
        """Title-cased multi-word names are redacted."""
        text = "John Michael Smith reported the issue."
        result = scrub_pii(text)
        assert "John Michael Smith" not in result
        assert "[NAME_REDACTED]" in result

    def test_scrub_ssn(self) -> None:
        """US SSN patterns are redacted."""
        text = "SSN on file: 123-45-6789."
        result = scrub_pii(text)
        assert "123-45-6789" not in result
        assert "[SSN_REDACTED]" in result

    def test_scrub_credit_card(self) -> None:
        """Credit card numbers are redacted."""
        text = "Card: 4111 1111 1111 1111 on the receipt."
        result = scrub_pii(text)
        assert "4111 1111 1111 1111" not in result
        assert "[CC_REDACTED]" in result

    def test_scrub_combined_pii(self) -> None:
        """Multiple PII types in one string are all redacted."""
        text = (
            "John Michael Smith called +1-555-123-4567 "
            "about email john.doe@fifa.org"
        )
        result = scrub_pii(text)

        # No raw PII should survive.
        assert "John Michael Smith" not in result
        assert "+1-555-123-4567" not in result
        assert "john.doe@fifa.org" not in result
        assert "555" not in result  # no phone fragments

        # Redaction tokens present.
        assert "[NAME_REDACTED]" in result
        assert "[PHONE_REDACTED]" in result
        assert "[EMAIL_REDACTED]" in result

    def test_scrub_clean_input(self) -> None:
        """Input with no PII passes through unchanged."""
        text = "All clear at this gate."
        result = scrub_pii(text)
        assert result == text


# ═══════════════════════════════════════════════════════════════════════
#  Telemetry Filter
# ═══════════════════════════════════════════════════════════════════════


class TestTelemetryFilter:
    """Tests for ``TelemetryFilter``."""

    @pytest.fixture
    def tf(self, settings: Settings) -> TelemetryFilter:
        return TelemetryFilter(settings)

    def test_threshold_crowd_alert(
        self,
        tf: TelemetryFilter,
        sample_raw_telemetry: RawTelemetry,
    ) -> None:
        """Turnstile count above threshold triggers a crowd alert."""
        result = tf.filter_telemetry(sample_raw_telemetry)
        assert any("CROWD_ALERT" in a for a in result.alerts)

    def test_threshold_density_alert(
        self,
        tf: TelemetryFilter,
        sample_raw_telemetry: RawTelemetry,
    ) -> None:
        """Crowd density > 85% triggers a density alert."""
        result = tf.filter_telemetry(sample_raw_telemetry)
        assert any("DENSITY_ALERT" in a for a in result.alerts)

    def test_threshold_heat_alert(
        self,
        tf: TelemetryFilter,
        sample_raw_telemetry: RawTelemetry,
    ) -> None:
        """Temperature above max triggers a heat alert."""
        result = tf.filter_telemetry(sample_raw_telemetry)
        assert any("HEAT_ALERT" in a for a in result.alerts)

    def test_pii_in_notes_scrubbed(
        self,
        tf: TelemetryFilter,
        sample_raw_telemetry: RawTelemetry,
    ) -> None:
        """PII in the ``notes`` field is scrubbed after filtering."""
        result = tf.filter_telemetry(sample_raw_telemetry)
        assert "John Michael Smith" not in result.notes
        assert "+1-555-123-4567" not in result.notes
        assert "john.doe@fifa.org" not in result.notes

    def test_no_alerts_below_threshold(self, tf: TelemetryFilter) -> None:
        """No alerts when all values are within normal ranges."""
        raw = RawTelemetry(
            gate_id="Gate-A",
            turnstile_count=200,
            crowd_density=0.5,
            temperature_c=30.0,
            humidity_pct=50.0,
            notes="All clear.",
            timestamp=datetime(2026, 7, 15, 14, 0, 0, tzinfo=timezone.utc),
        )
        result = tf.filter_telemetry(raw)
        assert result.alerts == []


# ═══════════════════════════════════════════════════════════════════════
#  Context Compression
# ═══════════════════════════════════════════════════════════════════════


class TestCompressContext:
    """Tests for ``TelemetryFilter.compress_context()``."""

    def test_compress_context_token_limit(
        self,
        sample_filtered_telemetry: FilteredTelemetry,
    ) -> None:
        """Compressed context respects the token budget."""
        max_tokens = 100
        result = TelemetryFilter.compress_context(
            sample_filtered_telemetry, max_tokens=max_tokens
        )
        # Rough check: 1 token ≈ 4 chars.
        assert len(result) <= max_tokens * 4

    def test_compress_context_includes_gate(
        self,
        sample_filtered_telemetry: FilteredTelemetry,
    ) -> None:
        """Compressed context includes the gate ID."""
        result = TelemetryFilter.compress_context(sample_filtered_telemetry)
        assert "Gate-C" in result


# ═══════════════════════════════════════════════════════════════════════
#  Stream Consumer
# ═══════════════════════════════════════════════════════════════════════


class TestEdgeStreamConsumer:
    """Tests for ``EdgeStreamConsumer``."""

    @pytest.mark.asyncio
    async def test_stream_consumer_yields_filtered(
        self,
        settings: Settings,
    ) -> None:
        """Consumer yields ``FilteredTelemetry`` instances, not raw data."""
        consumer = EdgeStreamConsumer(settings, interval_seconds=0.01)
        count = 0
        async for event in consumer.consume():
            assert isinstance(event, FilteredTelemetry)
            # Notes should never contain raw PII (the synthetic data
            # includes PII-laden notes that must be scrubbed).
            assert "john.doe@fifa.org" not in event.notes
            count += 1
            if count >= 3:
                consumer.stop()
                break
        assert count == 3

    @pytest.mark.asyncio
    async def test_latest_snapshot_populated(
        self,
        settings: Settings,
    ) -> None:
        """After consuming, ``get_latest_snapshot()`` returns data."""
        consumer = EdgeStreamConsumer(settings, interval_seconds=0.01)
        async for event in consumer.consume():
            break  # consume one event
        snapshot = consumer.get_latest_snapshot()
        assert snapshot is not None
        assert isinstance(snapshot, FilteredTelemetry)
