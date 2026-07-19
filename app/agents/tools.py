"""
OmniCrew AI — Strictly typed LangChain tools for the three sub-agent domains.

Each tool:
* Is decorated with ``@tool`` and has a tightly-scoped docstring (lean
  context window — the LLM sees *only* what it needs).
* Accepts a Pydantic v2 input schema with ``Field(description=...)``
  constraints.
* Returns a Pydantic v2 output schema, which is validated before the
  result is trusted downstream.
* Operates exclusively on **post-edge-filtered data** — it never touches
  raw IoT streams.

Design note:
    The tools are pure-logic stubs that simulate domain-specific
    reasoning.  In production they would call out to dedicated
    micro-services (crowd-management API, hospital dispatch, access-
    control database) via async HTTP.  Even as stubs, they enforce full
    schema validation so the rest of the architecture can rely on typed
    contracts.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from langchain_core.tools import tool


# ═══════════════════════════════════════════════════════════════════════
#  Input / Output Schemas
# ═══════════════════════════════════════════════════════════════════════


# ── Crowd Management ────────────────────────────────────────────────────


class CrowdQuery(BaseModel):
    """Input schema for the crowd-management tool."""

    gate: str = Field(
        ...,
        min_length=1,
        max_length=32,
        description="Gate identifier experiencing the crowd issue (e.g. 'Gate-C').",
    )
    issue: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Free-text description of the crowd issue (e.g. 'overflow', 'flooding').",
    )
    current_count: int | None = Field(
        default=None,
        ge=0,
        description="Current turnstile count at the gate, if known.",
    )


class CrowdResponse(BaseModel):
    """Output schema for the crowd-management tool."""

    recommendation: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Actionable recommendation for ground staff.",
    )
    alternative_gates: list[str] = Field(
        default_factory=list,
        description="Ordered list of alternative gates to redirect overflow.",
    )
    estimated_wait_min: int = Field(
        ...,
        ge=0,
        le=180,
        description="Estimated wait time in minutes at the affected gate.",
    )
    severity: str = Field(
        ...,
        description="Severity level: 'low', 'medium', 'high', or 'critical'.",
    )


# ── Medical Assistance ──────────────────────────────────────────────────


class MedicalQuery(BaseModel):
    """Input schema for the medical-assistance tool."""

    location: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Location of the medical incident (e.g. 'Section 204, Row F').",
    )
    issue_type: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Type of medical issue (e.g. 'heat exhaustion', 'cardiac event').",
    )
    severity: str = Field(
        ...,
        description="Severity: 'minor', 'moderate', 'severe', 'life-threatening'.",
    )
    patient_count: int = Field(
        ...,
        ge=1,
        le=100,
        description="Number of patients requiring assistance.",
    )


class MedicalResponse(BaseModel):
    """Output schema for the medical-assistance tool."""

    instructions: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Step-by-step medical response instructions.",
    )
    nearest_station: str = Field(
        ...,
        min_length=1,
        max_length=100,
        description="Name / ID of the nearest medical station.",
    )
    eta_min: int = Field(
        ...,
        ge=0,
        le=60,
        description="Estimated time of arrival for the medical team in minutes.",
    )
    escalation_needed: bool = Field(
        ...,
        description="Whether the incident requires escalation to external EMS.",
    )


# ── Access Control ──────────────────────────────────────────────────────


class AccessQuery(BaseModel):
    """Input schema for the access-control tool."""

    zone: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Zone or area in question (e.g. 'VIP Lounge East').",
    )
    issue: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Description of the access issue (e.g. 'credential denied at scanner').",
    )
    credential_type: str | None = Field(
        default=None,
        max_length=64,
        description="Type of credential presented (e.g. 'RFID badge', 'QR ticket').",
    )


class AccessResponse(BaseModel):
    """Output schema for the access-control tool."""

    action: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="Recommended action for the staff member.",
    )
    alternative_route: str | None = Field(
        default=None,
        max_length=200,
        description="Alternative entry route if the primary route is blocked.",
    )
    security_level: str = Field(
        ...,
        description="Current security level for the zone: 'normal', 'elevated', 'lockdown'.",
    )
    notify_command: bool = Field(
        ...,
        description="Whether the command center should be notified.",
    )


# ═══════════════════════════════════════════════════════════════════════
#  Tool Definitions
# ═══════════════════════════════════════════════════════════════════════

# Gate adjacency map used by the crowd-management tool to recommend
# overflow routing.  In production this would come from a spatial
# database.
_GATE_ADJACENCY: dict[str, list[str]] = {
    "Gate-A": ["Gate-B", "Gate-F"],
    "Gate-B": ["Gate-A", "Gate-C"],
    "Gate-C": ["Gate-B", "Gate-D"],
    "Gate-D": ["Gate-C", "Gate-E"],
    "Gate-E": ["Gate-D", "Gate-F"],
    "Gate-F": ["Gate-E", "Gate-A"],
}

# Medical station lookup.  In production this would be a GIS query.
_MEDICAL_STATIONS: dict[str, str] = {
    "Gate-A": "Med-Station Alpha",
    "Gate-B": "Med-Station Alpha",
    "Gate-C": "Med-Station Bravo",
    "Gate-D": "Med-Station Bravo",
    "Gate-E": "Med-Station Charlie",
    "Gate-F": "Med-Station Charlie",
    "Section 100": "Med-Station Alpha",
    "Section 200": "Med-Station Bravo",
    "Section 300": "Med-Station Charlie",
}


@tool
def crowd_management(gate: str, issue: str, current_count: int | None = None) -> dict:
    """Analyse a crowd issue at a specific gate and recommend overflow routing.

    Use this tool when a staff member reports crowding, flooding, congestion,
    or capacity issues at a stadium gate.

    Args:
        gate: Gate identifier (e.g. 'Gate-C').
        issue: Description of the crowd issue.
        current_count: Current turnstile count, if known.
    """
    # Validate input via schema.
    query = CrowdQuery(gate=gate, issue=issue, current_count=current_count)

    # Determine severity from count / keywords.
    severity = "low"
    wait_min = 5
    if query.current_count is not None and query.current_count > 800:
        severity = "high"
        wait_min = 25
    elif query.current_count is not None and query.current_count > 500:
        severity = "medium"
        wait_min = 15

    issue_lower = query.issue.lower()
    if any(kw in issue_lower for kw in ("flood", "emergency", "critical", "crush")):
        severity = "critical"
        wait_min = 40

    alternatives = _GATE_ADJACENCY.get(query.gate, ["Gate-A", "Gate-B"])
    recommendation = (
        f"Redirect foot traffic from {query.gate} to "
        f"{', '.join(alternatives)}.  Deploy additional ushers to "
        f"manage flow.  Current severity: {severity}."
    )

    response = CrowdResponse(
        recommendation=recommendation,
        alternative_gates=alternatives,
        estimated_wait_min=wait_min,
        severity=severity,
    )
    return response.model_dump()


@tool
def medical_assistance(
    location: str,
    issue_type: str,
    severity: str,
    patient_count: int,
) -> dict:
    """Dispatch medical assistance and provide first-response instructions.

    Use this tool when a staff member reports an injury, illness, or medical
    emergency at any stadium location.

    Args:
        location: Where the incident is (e.g. 'Section 204, Row F').
        issue_type: Type of medical issue (e.g. 'heat exhaustion').
        severity: 'minor', 'moderate', 'severe', or 'life-threatening'.
        patient_count: Number of patients needing help.
    """
    query = MedicalQuery(
        location=location,
        issue_type=issue_type,
        severity=severity,
        patient_count=patient_count,
    )

    # Find nearest station (fuzzy match on first matching key prefix).
    nearest = "Med-Station Alpha"  # default
    for prefix, station in _MEDICAL_STATIONS.items():
        if prefix.lower() in query.location.lower():
            nearest = station
            break

    escalation = query.severity in ("severe", "life-threatening") or query.patient_count > 3
    eta = 3 if query.severity == "life-threatening" else 5 if query.severity == "severe" else 10

    instructions = (
        f"Medical team dispatched from {nearest} — ETA {eta} min.  "
        f"Issue: {query.issue_type} ({query.severity}).  "
        f"{'Call external EMS immediately.' if escalation else 'Standard first-aid protocol.'} "
        f"Patients: {query.patient_count}."
    )

    response = MedicalResponse(
        instructions=instructions,
        nearest_station=nearest,
        eta_min=eta,
        escalation_needed=escalation,
    )
    return response.model_dump()


@tool
def access_control(
    zone: str,
    issue: str,
    credential_type: str | None = None,
) -> dict:
    """Resolve access-control issues for a specific zone.

    Use this tool when a staff member reports credential denials, scanner
    failures, or restricted-zone access questions.

    Args:
        zone: Zone or area (e.g. 'VIP Lounge East').
        issue: Description of the access issue.
        credential_type: Type of credential, if known (e.g. 'RFID badge').
    """
    query = AccessQuery(zone=zone, issue=issue, credential_type=credential_type)

    issue_lower = query.issue.lower()

    # Determine security posture.
    if any(kw in issue_lower for kw in ("lockdown", "threat", "breach")):
        security_level = "lockdown"
        notify = True
        action = (
            f"LOCKDOWN — {query.zone} is under restricted access.  "
            "Deny all entry, hold position, await command-center instructions."
        )
        alt_route = None
    elif any(kw in issue_lower for kw in ("denied", "fail", "reject", "invalid")):
        security_level = "normal"
        notify = False
        action = (
            f"Credential issue at {query.zone}.  "
            f"{'Try manual verification of ' + query.credential_type + '.' if query.credential_type else 'Request manual ID verification.'} "
            "If verification fails, redirect to Guest Services."
        )
        alt_route = "Guest Services Desk — Main Concourse"
    else:
        security_level = "normal"
        notify = False
        action = (
            f"Standard access inquiry for {query.zone}.  "
            "Verify credentials and allow entry if valid."
        )
        alt_route = None

    response = AccessResponse(
        action=action,
        alternative_route=alt_route,
        security_level=security_level,
        notify_command=notify,
    )
    return response.model_dump()


# Convenience list for binding to the LLM / ToolNode.
ALL_TOOLS = [crowd_management, medical_assistance, access_control]
