import json

from api.utils import build_analysis_reports_payload
from tradingagents.graph.propagation import Propagator
from tradingagents.graph.trading_graph import TradingAgentsGraph


def _sample_bundle_dict():
    return {
        "ticker": "MU",
        "company_name": "Micron Technology",
        "as_of": "2026-05-04",
        "recent_events": [
            {
                "event_id": "evt_001",
                "ticker": "MU",
                "event_type": "earnings_result",
                "event_time": "2026-05-01T20:00:00Z",
                "detected_at": "2026-05-02T00:00:00Z",
                "source": "news",
                "title": "Micron raises guidance",
                "summary": "Management lifted revenue guidance.",
                "url": "https://example.com/mu-guidance",
                "materiality_score": 0.82,
                "novelty_score": 0.9,
                "sentiment_score": 0.6,
                "confidence": 0.86,
            }
        ],
        "upcoming_events": [],
        "recent_filings": [
            {
                "accession_number": "0000000000-26-000001",
                "cik": "723125",
                "form_type": "8-K",
                "filing_date": "2026-05-02",
                "report_date": "2026-05-01",
                "primary_document_url": "https://example.com/8k",
                "filing_summary": "Guidance update.",
                "extracted_signals": ["guidance_raise"],
                "materiality_score": 0.8,
            }
        ],
        "macro_events": [
            {
                "event_name": "FOMC",
                "release_time": "2026-05-06T18:00:00Z",
                "series_or_release_id": None,
                "actual": None,
                "consensus": None,
                "previous": None,
                "surprise_score": None,
                "affected_sectors": ["semiconductors"],
                "relevance_to_ticker": 0.4,
            }
        ],
        "market_context": {
            "last_close": 120.5,
            "one_day_return_pct": 4.2,
            "five_day_return_pct": 9.5,
            "volume_ratio": 2.3,
            "price_volume_shock": True,
            "summary": "Breakout on elevated volume.",
        },
        "position_context": {
            "has_position": True,
            "position_size_pct": 0.12,
            "cost_basis": 100.0,
            "unrealized_pnl_pct": 20.5,
            "stop_loss": 108.0,
            "target_price": 135.0,
            "max_position_size_pct": 0.2,
            "holding_period": "1-2 weeks",
        },
        "prior_thesis": {
            "decision": "BUY",
            "thesis_summary": "Memory demand acceleration supports upside.",
            "bull_points": ["Guidance revisions improving"],
            "bear_points": ["Cyclical pricing risk"],
            "thesis_dependencies": ["Revenue acceleration"],
            "invalidation_conditions": ["Guidance cut"],
            "time_horizon": "1-2 weeks",
            "created_at": "2026-05-01T00:00:00Z",
        },
        "source_quality": {"news": {"status": "ok"}},
        "data_freshness": {"news": "2026-05-04T00:00:00Z"},
    }


def test_section_5_bundle_round_trips_and_defaults_optional_inputs():
    from tradingagents.schemas.catalyst_events import CatalystEventBundle

    bundle = CatalystEventBundle.from_dict(_sample_bundle_dict())
    reloaded = CatalystEventBundle.from_json(bundle.to_json())

    assert reloaded.ticker == "MU"
    assert reloaded.recent_events[0].event_type == "earnings_result"
    assert reloaded.recent_filings[0].form_type == "8-K"
    assert reloaded.macro_events[0].affected_sectors == ["semiconductors"]
    assert reloaded.position_context.has_position is True
    assert reloaded.prior_thesis.thesis_dependencies == ["Revenue acceleration"]

    minimal = CatalystEventBundle.from_dict({"ticker": "AAPL", "as_of": "2026-05-04"})
    assert minimal.company_name is None
    assert minimal.recent_events == []
    assert minimal.position_context is None
    assert minimal.market_context.summary == ""


def test_section_6_report_validates_allowed_values_and_evidence_table():
    from tradingagents.schemas.catalyst_events import CatalystEventReport

    report = CatalystEventReport.from_dict(
        {
            "ticker": "MU",
            "as_of": "2026-05-04",
            "event_risk_rating": "invalid",
            "catalyst_score": 1.5,
            "thesis_break_score": -0.2,
            "thesis_support_score": 0.7,
            "near_term_catalysts": ["earnings"],
            "recent_material_events": ["8-K guidance raise"],
            "thesis_supporting_events": ["guidance raise"],
            "thesis_breaking_events": [],
            "unresolved_questions": ["How durable is pricing?"],
            "recommended_action": "not_allowed",
            "action_rationale": "Malformed values should be made safe.",
            "risk_controls": ["do not chase"],
            "evidence_table": [
                {
                    "source": "8-K",
                    "event_type": "guidance_change",
                    "date": "2026-05-02",
                    "claim": "Guidance increased.",
                    "thesis_impact": "supporting",
                    "confidence": 1.2,
                    "url": "https://example.com/8k",
                }
            ],
        }
    )

    payload = json.loads(report.to_json())
    assert payload["event_risk_rating"] == "MEDIUM"
    assert payload["recommended_action"] == "continue_analysis"
    assert payload["catalyst_score"] == 1.0
    assert payload["thesis_break_score"] == 0.0
    assert payload["evidence_table"][0]["confidence"] == 1.0


def test_malformed_llm_output_produces_valid_fallback_report():
    from tradingagents.agents.analysts.catalyst_event_analyst import parse_catalyst_report

    report = parse_catalyst_report("not json", _sample_bundle_dict())

    assert report["ticker"] == "MU"
    assert report["event_risk_rating"] in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert report["recommended_action"] == "continue_analysis"
    assert isinstance(report["evidence_table"], list)


def test_initial_state_payload_and_order_include_catalyst_fields():
    state = Propagator().create_initial_state("MU", "2026-05-04")

    assert state["catalyst_report"] == ""
    assert state["catalyst_event_bundle"] == {}
    assert state["catalyst_event_report_structured"] == {}
    assert state["catalyst_ledger"]["analyst_domain"] == "catalyst"

    ordered = TradingAgentsGraph.normalize_selected_analysts(
        ["market", "news", "catalyst", "fundamentals"]
    )
    assert ordered == ["catalyst", "market", "news", "fundamentals"]

    reports = build_analysis_reports_payload(
        {
            "catalyst_report": "## Catalyst",
            "catalyst_event_bundle": {"ticker": "MU"},
            "catalyst_event_report_structured": {"event_risk_rating": "HIGH"},
            "catalyst_ledger": {"analyst_domain": "catalyst"},
            "catalyst_evidence": "Catalyst evidence",
        }
    )
    assert reports["catalyst_event_report_structured"]["event_risk_rating"] == "HIGH"
