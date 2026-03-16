from __future__ import annotations

import logging
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.configs.config import DefaultConfig
from app.core.logging import setup_logging

# Load configuration settings
CONFIG = DefaultConfig()

# Logger setup
setup_logging()
logger = logging.getLogger(__name__)


class BoardingPassData(BaseModel):
    airport_code: str | None = None
    destination_code: str | None = None
    destination_city: str | None = None
    terminal: str | None = None
    gate: str | None = None
    flight_number: str | None = None
    departure_time_local: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    assumptions: list[str] = Field(default_factory=list)


class Lounge(BaseModel):
    lounge_id: str
    name: str
    airport_code: str
    terminal: str | None = None
    opening_hours: str
    amenities: list[str] = Field(default_factory=list)
    access_notes: str = ""
    source_url: str


class RankedLounge(BaseModel):
    lounge: Lounge
    score: float
    rationale: list[str] = Field(default_factory=list)
    trade_offs: list[str] = Field(default_factory=list)


class AdvisoryResult(BaseModel):
    generated_at_utc: datetime
    recommendation: str
    destination_context: str
    guardrails: list[str]
    uncertainty_notes: list[str]
    lounge_id: str | None = None
    source_url: str | None = None


class PipelineRun(BaseModel):
    raw_text: str
    extracted: BoardingPassData
    lounges_found: list[Lounge] = Field(default_factory=list)
    ranked_lounges: list[RankedLounge] = Field(default_factory=list)
    advisory: AdvisoryResult | None = None
    status: Literal["ok", "needs_input", "error"] = "ok"
