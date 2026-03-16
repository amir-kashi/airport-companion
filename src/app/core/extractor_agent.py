from __future__ import annotations

import logging
import re
from datetime import datetime

from pydantic import BaseModel

from app.configs.config import DefaultConfig
from app.core.domain import BoardingPassData
from app.core.logging import setup_logging

# Load configuration settings
CONFIG = DefaultConfig()

# Logger setup
setup_logging()
logger = logging.getLogger(__name__)


class _ExtractionSchema(BaseModel):
    airport_code: str | None = None
    destination_code: str | None = None
    destination_city: str | None = None
    terminal: str | None = None
    gate: str | None = None
    flight_number: str | None = None
    departure_time_local: str | None = None


TERMINAL_HINTS: dict[str, dict[str, str]] = {
    "LHR": {
        "A": "3",
        "B": "5",
        "C": "5",
    },
    "DXB": {
        "A": "3",
        "B": "3",
        "C": "3",
        "D": "1",
        "F": "2",
    },
}


def _norm_iata(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().upper()
    return value if re.match(r"^[A-Z]{3}$", value) else None


def infer_terminal(
    airport_code: str | None, gate: str | None
) -> tuple[str | None, str | None]:
    if not airport_code or not gate:
        return None, None
    first_char = gate.strip().upper()[:1]
    inferred = TERMINAL_HINTS.get(airport_code.upper(), {}).get(first_char)
    if inferred:
        return (
            inferred,
            f"Terminal {inferred} inferred from gate {gate} at {airport_code}.",
        )
    return None, None


def _extract_with_regex(raw_text: str) -> BoardingPassData:
    text = raw_text.upper()
    iatas = re.findall(r"\b[A-Z]{3}\b", text)
    flight = re.search(r"\b([A-Z]{2}\s?\d{1,4})\b", text)
    gate = re.search(r"\bGATE\s*([A-Z]?\d{1,3})\b", text)
    terminal = re.search(r"\bTERMINAL\s*([A-Z]?\d{1,2})\b", text)
    dep = re.search(r"\b(\d{1,2}:\d{2})\b", text)

    airport = iatas[0] if iatas else None
    destination = iatas[1] if len(iatas) > 1 else None

    assumptions: list[str] = []
    final_terminal = terminal.group(1) if terminal else None
    if not final_terminal and airport and gate:
        inferred, note = infer_terminal(airport, gate.group(1))
        if inferred:
            final_terminal = inferred
            assumptions.append(note or "")

    return BoardingPassData(
        airport_code=_norm_iata(airport),
        destination_code=_norm_iata(destination),
        terminal=final_terminal,
        gate=(gate.group(1) if gate else None),
        flight_number=(flight.group(1).replace(" ", "") if flight else None),
        departure_time_local=(dep.group(1) if dep else None),
        confidence=0.6 if airport else 0.3,
        assumptions=[a for a in assumptions if a],
    )


def _extract_with_llm(raw_text: str) -> BoardingPassData | None:
    api_key = CONFIG.OPENAI_API_KEY
    if not api_key or not raw_text.strip():
        return None

    try:
        from openai import OpenAI
    except Exception:
        return None

    try:
        client = OpenAI(api_key=api_key)
        response = client.responses.parse(
            model=CONFIG.EXTRACT_MODEL,
            input=[
                {
                    "role": "system",
                    "content": (
                        "Extract boarding pass fields. "
                        "Use null when a field is unknown. "
                        "departure_time_local must be HH:MM when present."
                    ),
                },
                {"role": "user", "content": raw_text},
            ],
            text_format=_ExtractionSchema,
        )
        parsed = response.output_parsed
        if not parsed:
            return None
        return BoardingPassData(
            airport_code=_norm_iata(parsed.airport_code),
            destination_code=_norm_iata(parsed.destination_code),
            destination_city=parsed.destination_city,
            terminal=(parsed.terminal or None),
            gate=(parsed.gate or None),
            flight_number=(parsed.flight_number or None),
            departure_time_local=(parsed.departure_time_local or None),
            confidence=0.85,
            assumptions=[],
        )
    except Exception:
        return None


def enrich_terminal_if_missing(data: BoardingPassData) -> BoardingPassData:
    if data.terminal:
        return data
    inferred, note = infer_terminal(data.airport_code, data.gate)
    if inferred:
        data.terminal = inferred
        if note:
            data.assumptions.append(note)
            data.confidence = min(data.confidence, 0.75)
    return data


def extract_boarding_pass_fields(raw_text: str) -> BoardingPassData:
    llm = _extract_with_llm(raw_text)
    data = llm if llm else _extract_with_regex(raw_text)
    data = enrich_terminal_if_missing(data)
    if data.departure_time_local:
        try:
            datetime.strptime(data.departure_time_local, "%H:%M")
        except ValueError:
            data.assumptions.append("Departure time format uncertain.")
            data.departure_time_local = None
            data.confidence = min(data.confidence, 0.55)
    return data
