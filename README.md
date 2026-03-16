# Boarding Pass OCR - Nearest Lounge & Destination Advisor

Streamlit prototype: upload a boarding pass image, extract key flight fields, discover internet-sourced lounges, rank options, and produce a concise travel advisory with explicit assumptions.

## Why Streamlit

- Zero-friction demo flow
- Single codebase with visible reasoning trace
- Fast iteration without sacrificing modular architecture

## Product Flow

- Scan tab:
	- Upload boarding pass image
	- OCR output shown directly
	- Manual fallback text input for low-confidence OCR
- Analysis tab:
	- Structured extraction result
	- Agent notes (assumptions, confidence, trade-offs)
	- Lounge candidates and ranking rationale
- Advisory tab:
	- Final lounge recommendation
	- Destination context and arrival estimate
	- Guardrails, citations, and uncertainty disclosure

## Internal Architecture

- `src/app/core/ocr_service.py`
	- OCR entry point
	- Uses OpenAI vision when configured
	- Falls back to manual text input
- `src/app/core/extractor_agent.py`
	- Parses airport, destination, terminal, gate, flight number, departure time
	- LLM-first extraction with regex fallback
	- Terminal inference from airport/gate conventions (best effort)
- `src/app/core/discovery_engine.py`
	- Public internet lounge discovery via Tavily search
	- Normalizes lounge records and ranks by constraints
	- Opening-hours overlap filtering (now to departure)
- `src/app/core/advisory_agent.py`
	- Builds concise recommendation + destination context
	- Adds guardrails and uncertainty disclosures

## Setup

1. Install dependencies:

```bash
uv sync
```

2. Configure environment variables as needed:

```env
OPENAI_API_KEY=...
TAVILY_API_KEY=...
OCR_MODEL=gpt-4.1-mini
EXTRACT_MODEL=gpt-4.1-mini
```

3. Run the app:

```bash
uv run streamlit run src/app/main.py
```

## Test Coverage (Minimal)

- Opening-hours overlap filter
- Advisory includes lounge recommendation and destination context

Run tests:

```bash
uv run pytest
```

## Notes and Trade-offs

- Lounge discovery requires a search provider key (`TAVILY_API_KEY`) for internet-sourced results.
- Terminal inference is heuristic and intentionally disclosed in advisory notes.
- Gate is treated as informational only; advisory warns about gate-change risk.

## Suggested Demo Scenarios

1. Complete boarding pass with terminal present.
2. Missing terminal, inferred from gate convention.
3. No eligible lounge found, advisory explains constraints.
