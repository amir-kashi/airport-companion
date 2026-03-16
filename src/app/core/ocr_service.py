from __future__ import annotations

import base64
import logging

from pydantic import BaseModel, Field

from app.configs.config import DefaultConfig
from app.core.domain import BoardingPassData
from app.core.logging import setup_logging

# Load configuration settings
CONFIG = DefaultConfig()

# Logger setup
setup_logging()
logger = logging.getLogger(__name__)


class _OcrData(BaseModel):
    raw_text: str | None = None
    ocr_conf: float = Field(default=0.0, ge=0.0, le=1.0)


def run_ocr(
    image_bytes: bytes | None, fallback_text: str = ""
) -> tuple[str, float, list[str]]:
    if fallback_text.strip():
        return fallback_text.strip(), 1.0, ["Used manual text input fallback."]

    if not image_bytes:
        return "", 0.0, ["No image provided."]

    api_key = CONFIG.OPENAI_API_KEY
    logger.debug(f"API Key present: {bool(api_key)}")
    if not api_key:
        return (
            "",
            0.0,
            ["OPENAI_API_KEY is missing. OCR skipped; manual text input required."],
        )

    try:
        from openai import OpenAI
    except Exception:
        return "", 0.0, ["OpenAI package unavailable. OCR skipped."]

    try:
        client = OpenAI(api_key=api_key)
        base64_img = base64.b64encode(image_bytes).decode("ascii")

        response = client.responses.parse(
            model=CONFIG.OCR_MODEL,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Extract the raw text and confidence score from the "
                                "following image of a boarding pass. The confidence "
                                "score should be a float between 0 and 1, "
                                "representing the OCR model's confidence in the "
                                "extracted text. If the text cannot be extracted, "
                                "return an empty string for raw_text and a confidence "
                                "score of 0."
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{base64_img}",
                        },
                    ],
                }
            ],
            text_format=_OcrData,
        )
        text = (response.output_parsed.raw_text or "").strip()
        confidence = response.output_parsed.ocr_conf
        notes = (
            ["OCR completed via OpenAI Vision model."]
            if text
            else ["OCR returned no text."]
        )
        return text, confidence, notes
    except Exception as exc:
        return "", 0.0, [f"OCR failure: {exc}"]


def needs_manual_fallback(extracted: BoardingPassData) -> bool:
    required = [
        extracted.airport_code,
        extracted.flight_number,
        extracted.departure_time_local,
    ]
    return any(not value for value in required) or extracted.confidence < 0.5
