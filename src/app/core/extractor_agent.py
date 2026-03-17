from __future__ import annotations

import logging
import re
from datetime import time

from app.configs.config import DefaultConfig
from app.core.domain import BoardingPassData
from app.core.logging import setup_logging

# Load configuration settings
CONFIG = DefaultConfig()

# Logger setup
setup_logging()
logger = logging.getLogger(__name__)


def _norm_iata(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip().upper()
    return value if re.match(r"^[A-Z]{3}$", value) else None


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
            text_format=BoardingPassData,
        )
        parsed = response.output_parsed
        print("LLM parsed output:\n", vars(parsed) if parsed else "None")
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
            confidence=parsed.confidence or 0.0,
            assumptions=parsed.assumptions or [],
        )
    except Exception:
        return None


def extract_boarding_pass_fields(raw_text: str) -> BoardingPassData:
    data = _extract_with_llm(raw_text)
    if not data:
        return BoardingPassData(
            confidence=0.0,
            assumptions=["No data extracted from raw text."],
        )
    if data and data.departure_time_local:
        try:
            time.fromisoformat(data.departure_time_local)
        except ValueError:
            data.assumptions.append("Departure time format uncertain.")
    return data
