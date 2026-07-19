"""
OmniCrew AI — Crypto helpers, token validation, PII masking for logs,
input sanitization, and prompt-injection heuristic detection.

This module provides *lightweight* security utilities that run on every
request path.  Heavy PII scrubbing for the edge boundary lives in
``app.edge.filter``.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import string
from typing import Final

from app.config import Settings, get_settings

# ── Constants ────────────────────────────────────────────────────────────

# Minimum acceptable API-key length (prefix + body).
_MIN_KEY_LENGTH: Final[int] = 16
# Characters allowed in API keys.
_KEY_CHARSET: Final[set[str]] = set(string.ascii_letters + string.digits + "-_")

# Lightweight PII patterns for *log* masking (middle-portion redaction).
_LOG_PHONE_RE: Final[re.Pattern[str]] = re.compile(
    r"(\+?\d{1,3}[-.\s]?)(\(?\d{2,4}\)?[-.\s]?\d{2,4}[-.\s]?\d{2,9})"
)
_LOG_EMAIL_RE: Final[re.Pattern[str]] = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)

# Common prompt-injection phrases (case-insensitive).
_INJECTION_PATTERNS: Final[list[tuple[str, re.Pattern[str]]]] = [
    (
        "ignore_previous",
        re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+instructions", re.IGNORECASE),
    ),
    (
        "reveal_system_prompt",
        re.compile(r"(reveal|show|print|output|repeat)\s+(your\s+)?(system\s+)?(prompt|instructions)", re.IGNORECASE),
    ),
    (
        "role_override",
        re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    ),
    (
        "embedded_system_tag",
        re.compile(r"<\s*system\s*>", re.IGNORECASE),
    ),
    (
        "embedded_tool_json",
        re.compile(r"\{\s*\"(tool_call|function_call|name)\"\s*:", re.IGNORECASE),
    ),
    (
        "jailbreak_dan",
        re.compile(r"(DAN|do\s+anything\s+now)", re.IGNORECASE),
    ),
]

# Control characters to strip (keep newline/tab for readability).
_CONTROL_CHAR_RE: Final[re.Pattern[str]] = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]"
)


# ── API-Key Validation ───────────────────────────────────────────────────


def validate_api_key_format(key: str) -> bool:
    """Check structural validity of an API key.

    Returns ``True`` if the key meets minimum length and charset
    requirements.  This does **not** verify the key against any registry —
    use ``hash_api_key`` + lookup for that.
    """
    if len(key) < _MIN_KEY_LENGTH:
        return False
    return all(ch in _KEY_CHARSET for ch in key)


def hash_api_key(key: str, *, settings: Settings | None = None) -> str:
    """Produce an HMAC-SHA256 hex digest of *key*.

    The HMAC secret is sourced from ``Settings.hmac_secret`` so that hashed
    keys remain consistent across restarts (but never appear in plaintext
    in logs or storage).
    """
    if settings is None:
        settings = get_settings()
    return hmac.new(
        key=settings.hmac_secret.encode("utf-8"),
        msg=key.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()


# ── PII Masking for Logs ────────────────────────────────────────────────


def mask_pii_for_logging(text: str) -> str:
    """Lightly mask PII in text destined for application logs.

    Unlike ``edge.filter.scrub_pii`` (which fully redacts), this function
    preserves the first and last characters of each detected value so that
    engineers can correlate log entries during debugging without exposing
    full PII.

    Examples::

        mask_pii_for_logging("+1-555-123-4567")
        # → "+1-***-***-***7"

        mask_pii_for_logging("john.doe@fifa.org")
        # → "j*******e@f******g"
    """

    def _partial_mask(match: re.Match[str]) -> str:
        val = match.group()
        if len(val) <= 2:
            return val
        return val[0] + "*" * (len(val) - 2) + val[-1]

    result = _LOG_PHONE_RE.sub(_partial_mask, text)
    result = _LOG_EMAIL_RE.sub(_partial_mask, result)
    return result


# ── Input Sanitization ──────────────────────────────────────────────────


def sanitize_input(text: str, max_length: int = 2000) -> str:
    """Clean raw user input before any downstream processing.

    1. Strips null bytes and non-printable control characters.
    2. Collapses runs of whitespace into single spaces.
    3. Strips leading/trailing whitespace.
    4. Truncates to *max_length* characters.

    This is the **first line of defence** — applied before the query
    reaches the LangGraph router.
    """
    cleaned = _CONTROL_CHAR_RE.sub("", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:max_length]


# ── Prompt-Injection Detection ──────────────────────────────────────────


def detect_injection_patterns(text: str) -> list[str]:
    """Scan *text* for common prompt-injection signatures.

    Returns a (possibly empty) list of pattern names that matched.  An
    empty list means no known injection patterns were detected.

    This is a **heuristic** layer — it catches low-sophistication attacks.
    High-sophistication attacks are mitigated architecturally (isolated
    system prompts, schema validation on tool outputs, user-input
    delimiters).
    """
    hits: list[str] = []
    for name, pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            hits.append(name)
    return hits
