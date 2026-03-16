from datetime import datetime

from app.core.advisory_agent import build_advisory
from app.core.discovery_engine import overlaps_now_to_departure
from app.core.domain import BoardingPassData, Lounge, RankedLounge
from app.core.extractor_agent import infer_terminal


def test_terminal_inference_from_gate():
    terminal, note = infer_terminal("LHR", "B12")
    assert terminal == "5"
    assert note is not None


def test_hours_overlap_window():
    now = datetime(2026, 3, 13, 15, 0)
    dep = datetime(2026, 3, 13, 17, 30)
    assert overlaps_now_to_departure("05:00-22:00", now, dep)
    assert not overlaps_now_to_departure("23:00-23:30", now, dep)


def test_advisory_includes_lounge_and_destination_context():
    extracted = BoardingPassData(
        airport_code="LHR",
        destination_code="DXB",
        terminal="5",
        gate="B12",
        flight_number="BA105",
        departure_time_local="18:10",
        confidence=0.9,
    )
    lounge = Lounge(
        lounge_id="LHR-1",
        name="Galleries Club Lounge",
        airport_code="LHR",
        terminal="5",
        opening_hours="05:00-22:00",
        amenities=["Wi-Fi", "Showers"],
        access_notes="Business class or status.",
        source_url="https://example.com/lounge",
    )
    ranked = [
        RankedLounge(
            lounge=lounge,
            score=2.5,
            rationale=["Same terminal as departure."],
            trade_offs=[],
        )
    ]

    result = build_advisory(extracted, ranked)
    assert "Recommended lounge:" in result.recommendation
    assert "Destination:" in result.destination_context
    assert result.lounge_id == "LHR-1"
    assert result.source_url == "https://example.com/lounge"
