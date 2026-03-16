from __future__ import annotations

import base64
import logging

from app.configs.config import DefaultConfig
from app.core.domain import BoardingPassData
from app.core.logging import setup_logging

# Load configuration settings
CONFIG = DefaultConfig()

# Logger setup
setup_logging()
logger = logging.getLogger(__name__)


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

        response = client.responses.create(
            model=CONFIG.OCR_MODEL,
            input=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "input_text",
                            "text": (
                                "Extract all text from this boarding pass exactly as written. "
                                "Return plain text only."
                                "If the image is not a boarding pass, return an empty string."
                            ),
                        },
                        {
                            "type": "input_image",
                            "image_url": f"data:image/png;base64,{base64_img}",
                        },
                    ],
                }
            ],
        )
        text = (response.output_text or "").strip()
        confidence = 0.9 if text else 0.0
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
