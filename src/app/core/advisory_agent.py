from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from app.configs.config import DefaultConfig
from app.core.domain import AdvisoryResult, BoardingPassData, RankedLounge
from app.core.logging import setup_logging

# Load configuration settings
CONFIG = DefaultConfig()

# Logger setup
setup_logging()
logger = logging.getLogger(__name__)


def _duration_note(flight_number: str | None) -> str:
    if not flight_number:
        return "Flight duration uncertain from available data."
    return "Likely short- to medium-haul unless route indicates otherwise."


def build_advisory(
    extracted: BoardingPassData,
    ranked_lounges: list[RankedLounge],
    now_local: datetime | None = None,
) -> AdvisoryResult:
    now_local = now_local or datetime.now()
    guardrails: list[str] = []
    uncertainty: list[str] = list(extracted.assumptions)

    top = ranked_lounges[0] if ranked_lounges else None
    if not top:
        recommendation = "No eligible lounge found from available public sources for the current constraints."
        guardrails.append(
            "No lounge recommendation made due to missing or ineligible candidates."
        )
        lounge_id = None
        source_url = None
    else:
        lounge = top.lounge
        why_parts = top.rationale + top.trade_offs
        reason = (
            " ".join(why_parts) if why_parts else "Best score among viable lounges."
        )
        recommendation = (
            f"Recommended lounge: {lounge.name} (Terminal {lounge.terminal or 'Unknown'}). "
            f"Hours: {lounge.opening_hours}. Gate: {extracted.gate or 'Unknown'}. "
            f"Amenities: {', '.join(lounge.amenities) if lounge.amenities else 'Not listed'}. "
            f"Why: {reason}"
        )
        lounge_id = lounge.lounge_id
        source_url = lounge.source_url
        guardrails.append(f"Cited lounge_id={lounge_id} and source_url={source_url}.")

    arrival_note = "Arrival time uncertain."
    if extracted.departure_time_local:
        try:
            hh, mm = extracted.departure_time_local.split(":")
            dep = now_local.replace(
                hour=int(hh), minute=int(mm), second=0, microsecond=0
            )
            arr = dep + timedelta(hours=3)
            arrival_note = f"Estimated arrival local at destination: around {arr.strftime('%H:%M')} (rough estimate)."
        except Exception:
            uncertainty.append("Could not infer arrival estimate from departure time.")

    destination = (
        extracted.destination_code
        or extracted.destination_city
        or "Unknown destination"
    )
    destination_context = f"Destination: {destination}. {_duration_note(extracted.flight_number)} {arrival_note}"

    if not extracted.terminal:
        uncertainty.append(
            "Terminal missing from boarding pass; recommendation may require revalidation."
        )
    if extracted.gate:
        guardrails.append(
            "Gate can change. Recheck airport monitors before heading to lounge."
        )

    return AdvisoryResult(
        generated_at_utc=datetime.now(UTC),
        recommendation=recommendation,
        destination_context=destination_context,
        guardrails=guardrails,
        uncertainty_notes=uncertainty,
        lounge_id=lounge_id,
        source_url=source_url,
    )
