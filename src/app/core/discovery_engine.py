from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta

from pydantic import BaseModel, Field

from app.configs.config import DefaultConfig
from app.core.domain import BoardingPassData, Lounge, RankedLounge
from app.core.logging import setup_logging

# Load configuration settings
CONFIG = DefaultConfig()

# Logger setup
setup_logging()
logger = logging.getLogger(__name__)


def _parse_hours(opening_hours: str) -> tuple[int, int] | None:
    match = re.search(r"(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})", opening_hours)
    if not match:
        return None
    h1, m1, h2, m2 = [int(v) for v in match.groups()]
    return h1 * 60 + m1, h2 * 60 + m2


def overlaps_now_to_departure(
    opening_hours: str, now_local: datetime, departure_local: datetime
) -> bool:
    parsed = _parse_hours(opening_hours)
    if not parsed:
        return True
    start_min, end_min = parsed
    now_min = now_local.hour * 60 + now_local.minute
    dep_min = departure_local.hour * 60 + departure_local.minute

    if end_min < start_min:
        end_min += 24 * 60
        if now_min < start_min:
            now_min += 24 * 60
        if dep_min < start_min:
            dep_min += 24 * 60

    return max(start_min, now_min) <= min(end_min, dep_min)


def _extract_terminal_hint(text: str) -> str | None:
    match = re.search(r"\bterminal\s*([a-z]?\d{1,2})\b", text, re.IGNORECASE)
    return match.group(1).upper() if match else None


class _Lounge(BaseModel):
    name: str
    opening_hours: str
    amenities: list[str] = Field(default_factory=list)
    access_notes: str = ""


def _extract_with_llm(title: str, content: str, raw_content: str) -> _Lounge | None:
    api_key = CONFIG.OPENAI_API_KEY
    if not api_key:
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
                    "content": ("Extract lounge information. "),
                },
                {"role": "user", "content": f"{title}\n{content}\n{raw_content}"},
            ],
            text_format=_Lounge,
        )
        parsed = response.output_parsed
        print("LLM parsed output:\n", vars(parsed) if parsed else "None")
        if not parsed:
            return None
        return _Lounge(
            name=parsed.name,
            opening_hours=parsed.opening_hours,
            amenities=parsed.amenities or [],
            access_notes=parsed.access_notes or "",
        )
    except Exception:
        return None


def discover_lounges(
    airport_code: str, terminal: str | None = None
) -> tuple[list[Lounge], list[str]]:
    notes: list[str] = []
    if not airport_code:
        return [], ["Airport code is missing; lounge discovery skipped."]

    tavily_key = CONFIG.TAVILY_API_KEY
    if not tavily_key:
        notes.append("TAVILY_API_KEY missing; internet lounge discovery unavailable.")
        return [], notes

    try:
        from tavily import TavilyClient
    except Exception:
        return [], ["tavily-python package unavailable; discovery skipped."]

    query = f"{airport_code} airport lounges terminal {terminal or ''} opening hours amenities"
    try:
        client = TavilyClient(api_key=tavily_key)
        resp = client.search(query=query, max_results=8)
        lounges: list[Lounge] = []
        for idx, item in enumerate(resp.get("results", []), start=1):
            title = item.get("title", "")
            content = item.get("content", "")
            raw_content = item.get("raw_content", "")
            lounge_info = _extract_with_llm(title, content, raw_content)

            term = _extract_terminal_hint(f"{title} {content}")
            # lounge_name = title.split("|")[0].strip() or f"Lounge {idx}"
            lounges.append(
                Lounge(
                    lounge_id=f"{airport_code}-{term or 'Unknown'}-{idx}",
                    name=(
                        lounge_info.name
                        if lounge_info
                        else title.strip() or f"Lounge {idx}"
                    ),
                    airport_code=airport_code,
                    terminal=term,
                    opening_hours=(
                        lounge_info.opening_hours if lounge_info else "Unknown"
                    ),
                    amenities=lounge_info.amenities if lounge_info else ["Unknown"],
                    access_notes=(
                        lounge_info.access_notes
                        if lounge_info
                        else "Verify access policy with your fare/status before entering."
                    ),
                    source_url=item.get("url", ""),
                )
            )
        notes.append(f"Found {len(lounges)} potential lounges from public web search.")
        return lounges, notes
    except Exception as exc:
        return [], [f"Lounge discovery error: {exc}"]


def rank_lounges(
    lounges: list[Lounge],
    flight: BoardingPassData,
    now_local: datetime | None = None,
) -> list[RankedLounge]:
    if not lounges:
        return []
    now_local = now_local or datetime.now()

    departure_dt = now_local + timedelta(hours=2)
    if flight.departure_time_local:
        try:
            hh, mm = flight.departure_time_local.split(":")
            departure_dt = now_local.replace(
                hour=int(hh), minute=int(mm), second=0, microsecond=0
            )
            if departure_dt < now_local:
                departure_dt = departure_dt + timedelta(days=1)
        except Exception as exc:
            logger.warning(
                f"Could not parse departure time '{flight.departure_time_local}': {exc}"
            )

    ranked: list[RankedLounge] = []
    for lounge in lounges:
        if lounge.airport_code != flight.airport_code:
            continue
        if not overlaps_now_to_departure(lounge.opening_hours, now_local, departure_dt):
            continue

        score = 0.0
        rationale: list[str] = []
        trade_offs: list[str] = []
        if flight.terminal and lounge.terminal and flight.terminal == lounge.terminal:
            score += 2.0
            rationale.append("Same terminal as departure.")
        elif flight.terminal and lounge.terminal and flight.terminal != lounge.terminal:
            score += 0.8
            trade_offs.append("Terminal crossing required; allow transfer buffer.")
        else:
            score += 1.0
            rationale.append("Terminal match unknown; treated as neutral.")

        if "24" in lounge.opening_hours:
            score += 0.5
            rationale.append("Extended opening hours.")

        ranked.append(
            RankedLounge(
                lounge=lounge,
                score=score,
                rationale=rationale,
                trade_offs=trade_offs,
            )
        )

    return sorted(ranked, key=lambda x: x.score, reverse=True)
