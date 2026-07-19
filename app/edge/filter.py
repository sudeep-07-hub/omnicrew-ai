"""
OmniCrew AI — Edge PII Scrubbing, Threshold Evaluation & Context Compression.

This module is the **security boundary** between raw IoT / ground-staff data
and the cloud LLM layer.  Nothing leaves this filter with PII intact.

Design principles:
* Deterministic regex-based scrubbing (no ML model dependency at the edge).
* Each PII category has its own redaction token so downstream consumers can
  tell *what* was removed without seeing *what* it contained.
* Threshold evaluation tags alerts so the LLM receives pre-digested context.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Final

from pydantic import BaseModel, Field

from app.config import Settings, get_settings

# ── PII Regex Patterns ──────────────────────────────────────────────────
#
# Each pattern maps to a redaction token.  Patterns are applied in order
# so that more specific patterns (e.g. credit-card) run before broader
# ones (e.g. phone-number fragments).

PII_PATTERNS: Final[dict[str, tuple[re.Pattern[str], str]]] = {
    "credit_card": (
        # Visa / MC / Amex with optional spaces or dashes.
        re.compile(
            r"\b(?:\d[ -]*?){13,19}\b"
        ),
        "[CC_REDACTED]",
    ),
    "ssn": (
        # US SSN: 123-45-6789 or 123 45 6789
        re.compile(r"\b\d{3}[-\s]\d{2}[-\s]\d{4}\b"),
        "[SSN_REDACTED]",
    ),
    "email": (
        re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"),
        "[EMAIL_REDACTED]",
    ),
    "phone": (
        # International formats: +1-555-123-4567, (555) 123-4567, etc.
        re.compile(
            r"(?:\+?\d{1,3}[-.\s]?)?"  # country code
            r"(?:\(?\d{2,4}\)?[-.\s]?)"  # area code
            r"\d{3,4}[-.\s]?\d{3,4}\b"  # subscriber
        ),
        "[PHONE_REDACTED]",
    ),
    "name": (
        # Title-cased multi-word sequences (≥2 words, each ≥2 chars).
        # Deliberately conservative to limit false positives.
        re.compile(r"\b(?:[A-Z][a-z]{1,20}\s){1,3}[A-Z][a-z]{1,20}\b"),
        "[NAME_REDACTED]",
    ),
}

# ── Pydantic Schemas ────────────────────────────────────────────────────


class RawTelemetry(BaseModel):
    """Schema for unfiltered data arriving from stadium edge sensors.

    The ``notes`` field carries free-text from ground staff and is the
    primary PII risk vector.
    """

    gate_id: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Identifier of the stadium gate (e.g. 'Gate-C').",
    )
    turnstile_count: int = Field(
        ...,
        ge=0,
        description="Cumulative turnstile entries since last reset.",
    )
    crowd_density: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Crowd density ratio (0 = empty, 1 = capacity).",
    )
    temperature_c: float = Field(
        ...,
        ge=-40.0,
        le=60.0,
        description="Ambient temperature in Celsius from on-site sensor.",
    )
    humidity_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Relative humidity percentage.",
    )
    notes: str = Field(
        default="",
        max_length=5000,
        description="Free-text notes from ground staff — PII scrubbing required.",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the telemetry reading.",
    )


class FilteredTelemetry(BaseModel):
    """Schema for scrubbed, threshold-evaluated telemetry safe for the
    cloud LLM layer.
    """

    gate_id: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Gate identifier (unchanged by filtering).",
    )
    turnstile_count: int = Field(
        ...,
        ge=0,
        description="Cumulative turnstile entries.",
    )
    crowd_density: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Crowd density ratio.",
    )
    temperature_c: float = Field(
        ...,
        ge=-40.0,
        le=60.0,
        description="Ambient temperature in Celsius.",
    )
    humidity_pct: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Relative humidity percentage.",
    )
    notes: str = Field(
        default="",
        max_length=5000,
        description="PII-scrubbed free-text notes.",
    )
    timestamp: datetime = Field(
        ...,
        description="UTC timestamp of the telemetry reading.",
    )
    alerts: list[str] = Field(
        default_factory=list,
        description="List of threshold-violation alerts generated at the edge.",
    )


# ── Core PII Scrubbing ──────────────────────────────────────────────────


def scrub_pii(text: str) -> str:
    """Apply all PII regex patterns and replace matches with redaction tokens.

    Patterns are applied in insertion order (credit_card → ssn → email →
    phone → name) so that more specific patterns take precedence.

    Args:
        text: Arbitrary free-text that may contain PII.

    Returns:
        A copy of *text* with every PII match replaced by its category
        redaction token (e.g. ``[PHONE_REDACTED]``).
    """
    result = text
    for _category, (pattern, token) in PII_PATTERNS.items():
        result = pattern.sub(token, result)
    return result


# ── Telemetry Filter ────────────────────────────────────────────────────


class TelemetryFilter:
    """Stateless filter that scrubs PII and evaluates edge thresholds.

    Usage::

        filt = TelemetryFilter(settings)
        clean = filt.filter_telemetry(raw_event)
        context_str = filt.compress_context(clean)
    """

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()

    def filter_telemetry(self, raw: RawTelemetry) -> FilteredTelemetry:
        """Scrub PII from *raw* and evaluate threshold alerts.

        This method is the **only gateway** from raw edge data to the
        cloud layer.  No other code path should bypass it.
        """
        alerts: list[str] = []

        # Threshold: crowd density / turnstile count.
        if raw.turnstile_count > self._settings.edge_crowd_threshold:
            alerts.append(
                f"CROWD_ALERT: {raw.gate_id} turnstile count "
                f"({raw.turnstile_count}) exceeds threshold "
                f"({self._settings.edge_crowd_threshold})."
            )

        if raw.crowd_density > 0.85:
            alerts.append(
                f"DENSITY_ALERT: {raw.gate_id} crowd density "
                f"({raw.crowd_density:.0%}) exceeds 85%."
            )

        # Threshold: temperature.
        if raw.temperature_c > self._settings.edge_temperature_max_c:
            alerts.append(
                f"HEAT_ALERT: {raw.gate_id} temperature "
                f"({raw.temperature_c:.1f}°C) exceeds "
                f"({self._settings.edge_temperature_max_c:.1f}°C)."
            )

        return FilteredTelemetry(
            gate_id=raw.gate_id,
            turnstile_count=raw.turnstile_count,
            crowd_density=raw.crowd_density,
            temperature_c=raw.temperature_c,
            humidity_pct=raw.humidity_pct,
            notes=scrub_pii(raw.notes),
            timestamp=raw.timestamp,
            alerts=alerts,
        )

    @staticmethod
    def compress_context(
        data: FilteredTelemetry,
        max_tokens: int = 500,
    ) -> str:
        """Compress filtered telemetry into a concise text summary for LLM
        context injection.

        The output is a structured block that fits within *max_tokens*
        (approximated as ``len(text) // 4`` characters-per-token).

        Args:
            data: A ``FilteredTelemetry`` instance.
            max_tokens: Approximate upper-bound token count.

        Returns:
            A human-readable summary string.
        """
        lines: list[str] = [
            f"[Telemetry — {data.gate_id} @ {data.timestamp.isoformat()}]",
            f"  Turnstile count : {data.turnstile_count}",
            f"  Crowd density   : {data.crowd_density:.0%}",
            f"  Temperature     : {data.temperature_c:.1f}°C",
            f"  Humidity        : {data.humidity_pct:.0f}%",
        ]
        if data.notes:
            lines.append(f"  Staff notes     : {data.notes}")
        if data.alerts:
            lines.append("  ⚠ Alerts:")
            for alert in data.alerts:
                lines.append(f"    - {alert}")

        summary = "\n".join(lines)

        # Rough token-budget enforcement (1 token ≈ 4 chars).
        max_chars = max_tokens * 4
        if len(summary) > max_chars:
            summary = summary[: max_chars - 3] + "..."

        return summary
