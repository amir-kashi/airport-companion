import logging

import streamlit as st

import app
from app.configs.config import DefaultConfig
from app.core.advisory_agent import build_advisory
from app.core.discovery_engine import discover_lounges, rank_lounges
from app.core.domain import AdvisoryResult, BoardingPassData, PipelineRun
from app.core.extractor_agent import extract_boarding_pass_fields
from app.core.logging import setup_logging
from app.core.ocr_service import needs_manual_fallback, run_ocr

# Load configuration settings
CONFIG = DefaultConfig()

# Logger setup
setup_logging()
logger = logging.getLogger(__name__)


def _init_state() -> None:
    st.session_state.setdefault("pipeline", None)
    st.session_state.setdefault("agent_notes", [])


def _run_pipeline(image_bytes: bytes | None, fallback_text: str) -> PipelineRun:
    notes: list[str] = []
    raw_text, ocr_conf, ocr_notes = run_ocr(
        image_bytes=image_bytes, fallback_text=fallback_text
    )
    notes.extend(ocr_notes)

    extracted = extract_boarding_pass_fields(raw_text)
    extracted.confidence = min(1.0, max(extracted.confidence, ocr_conf))
    notes.append(f"Extractor confidence: {extracted.confidence:.2f}")

    if needs_manual_fallback(extracted):
        notes.append("Low confidence extraction; user should verify/override fields.")

    lounges, discovery_notes = discover_lounges(
        airport_code=extracted.airport_code or "",
        terminal=extracted.terminal,
    )
    notes.extend(discovery_notes)

    ranked = rank_lounges(lounges, extracted)
    advisory: AdvisoryResult | None = build_advisory(extracted, ranked)

    status = "ok"
    if not raw_text:
        status = "needs_input"

    st.session_state["agent_notes"] = notes
    return PipelineRun(
        raw_text=raw_text,
        extracted=extracted,
        lounges_found=lounges,
        ranked_lounges=ranked,
        advisory=advisory,
        status=status,
    )


def _render_scan_tab() -> None:
    st.subheader("Boarding Pass OCR")
    uploaded = st.file_uploader(
        "Upload boarding pass image", type=["png", "jpg", "jpeg"]
    )
    fallback_text = st.text_area(
        "Fallback text input",
        placeholder="Paste boarding pass text if OCR is low confidence or unavailable.",
        height=140,
    )

    if st.button("Run Scan", type="primary"):
        image_bytes = uploaded.getvalue() if uploaded else None
        st.session_state["pipeline"] = _run_pipeline(image_bytes, fallback_text)

    pipeline: PipelineRun | None = st.session_state.get("pipeline")
    if pipeline:
        st.caption("Raw OCR/Text")
        st.code(pipeline.raw_text or "No OCR text extracted.", language="text")


def _render_analysis_tab() -> None:
    st.subheader("Agentic Analysis")
    pipeline: PipelineRun | None = st.session_state.get("pipeline")
    if not pipeline:
        st.info("Run Scan first.")
        return

    data: BoardingPassData = pipeline.extracted
    st.json(data.model_dump())

    st.markdown("### Reasoning Notes")
    for note in st.session_state.get("agent_notes", []):
        st.write(f"- {note}")

    st.markdown("### Lounge Candidates")
    if not pipeline.ranked_lounges:
        st.warning("No eligible lounges found under current constraints.")
        return

    for item in pipeline.ranked_lounges:
        st.write(
            f"- {item.lounge.name} | terminal={item.lounge.terminal or 'Unknown'} "
            f"| score={item.score:.2f} | source={item.lounge.source_url}"
        )


def _render_advisory_tab() -> None:
    st.subheader("Travel Companion Advisory")
    pipeline: PipelineRun | None = st.session_state.get("pipeline")
    if not pipeline or not pipeline.advisory:
        st.info("Run Scan first.")
        return

    advisory = pipeline.advisory
    st.markdown("### Lounge Recommendation")
    st.write(advisory.recommendation)

    st.markdown("### Destination Context")
    st.write(advisory.destination_context)

    st.markdown("### Guardrails")
    for line in advisory.guardrails:
        st.write(f"- {line}")

    if advisory.uncertainty_notes:
        st.markdown("### Assumptions & Uncertainty")
        for line in advisory.uncertainty_notes:
            st.write(f"- {line}")


def main() -> None:
    st.set_page_config(page_title="Boarding Pass Advisor", layout="wide")
    _init_state()

    st.title("Boarding Pass OCR - Nearest Lounge & Destination Advisor")
    st.caption(f"Version: {app.__version__}")

    tab_scan, tab_analysis, tab_advisory = st.tabs(["Scan", "Analysis", "Advisory"])
    with tab_scan:
        _render_scan_tab()
    with tab_analysis:
        _render_analysis_tab()
    with tab_advisory:
        _render_advisory_tab()


if __name__ == "__main__":
    main()
