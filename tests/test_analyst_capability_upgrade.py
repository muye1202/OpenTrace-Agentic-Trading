import json
import sqlite3
from pathlib import Path

import pytest

from tradingagents.agents.utils.agent_runtime.context_budget import (
    build_report_evidence_summary,
    format_analyst_evidence_context,
)
from tradingagents.agents.utils.market_data.bundle_tools import (
    format_evidence_bundle,
    select_bundle_first_tools,
)


class _Tool:
    def __init__(self, name):
        self.name = name


def test_bundle_first_tool_selection_exposes_only_bundle_on_first_round():
    bundle = _Tool("get_market_data_bundle")
    fallback = [_Tool("get_price_action_summary"), _Tool("get_indicators")]

    first_round = select_bundle_first_tools(bundle, fallback, enable_bundle_tools=True, rounds_used=0)
    fallback_round = select_bundle_first_tools(bundle, fallback, enable_bundle_tools=True, rounds_used=1)
    disabled = select_bundle_first_tools(bundle, fallback, enable_bundle_tools=False, rounds_used=0)

    assert [tool.name for tool in first_round] == ["get_market_data_bundle"]
    assert [tool.name for tool in fallback_round] == [
        "get_price_action_summary",
        "get_indicators",
    ]
    assert [tool.name for tool in disabled] == [
        "get_price_action_summary",
        "get_indicators",
    ]


def test_format_evidence_bundle_reduces_raw_sections_and_surfaces_missing_data():
    results = {
        "price_action_summary": "\n".join(
            [
                "## Price-action snapshot",
                "- Last close: 542.21 (prev: 517.16)",
                "- Returns: 5D 9.16% | 1M 47.40%",
                "- ATR(14): 28.94 (5.34% of price)",
                "| 20D high | 545.91 | breakout trigger |",
            ]
        ),
        "intraday_vwap_position": "No intraday data available for MU on 2026-05-04.",
        "raw_statement": "revenue,expense\n" + ("123,456\n" * 2000),
    }

    packet = format_evidence_bundle("Market Data Bundle", "MU", "2026-05-04", results, max_chars=1800)
    data = json.loads(packet)

    assert data["bundle"] == "Market Data Bundle"
    assert data["symbol"] == "MU"
    assert len(packet) <= 1800
    assert any("Last close" in fact["text"] for fact in data["facts"])
    assert any(item["section"] == "intraday_vwap_position" for item in data["missing_data"])
    assert "123,456\n123,456\n123,456" not in packet


def test_report_evidence_summary_strips_final_proposals_and_keeps_decision_evidence():
    report = """I now have all the data needed. Here is the complete report.

# MU Technical Report
- Price at $542.21 is above 10-EMA $500.54 and 50-SMA $425.57.
- ATR is 5.34% of price, so stops need room.
- Risk: no intraday VWAP data is available.

FINAL TRANSACTION PROPOSAL: BUY
"""

    summary = build_report_evidence_summary("market", report, max_chars=700)

    assert "FINAL TRANSACTION PROPOSAL" not in summary
    assert "I now have all the data" not in summary
    assert "Price at $542.21" in summary
    assert "no intraday VWAP data" in summary


def test_format_analyst_evidence_context_prefers_structured_evidence_over_raw_report():
    state = {
        "market_report": "RAW MARKET " * 2000,
        "market_evidence": "Market evidence: trend bullish, invalidation below 500.",
        "sentiment_report": "RAW SENTIMENT " * 2000,
        "news_report": "",
        "fundamentals_report": "",
    }

    context = format_analyst_evidence_context(state, max_chars_per_report=500)

    assert "Market evidence: trend bullish" in context
    assert "RAW MARKET RAW MARKET" not in context
    assert len(context) < 1400


def test_saved_trading_history_reports_can_be_compacted_without_vendor_calls():
    db_path = Path("trading_history.db")
    if not db_path.exists():
        pytest.skip("local trading_history.db not present")

    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    row = con.execute(
        "SELECT reports FROM analysis_sessions ORDER BY id DESC LIMIT 1"
    ).fetchone()
    con.close()
    assert row is not None

    reports = json.loads(row["reports"])
    state = {
        "market_report": reports.get("market_report", ""),
        "sentiment_report": reports.get("sentiment_report", ""),
        "news_report": reports.get("news_report", ""),
        "fundamentals_report": reports.get("fundamentals_report", ""),
    }

    context = format_analyst_evidence_context(state, max_chars_per_report=900)

    assert len(context) < sum(len(str(state[key])) for key in state)
    assert "FINAL TRANSACTION PROPOSAL" not in context
    assert "Analyst Evidence Context" in context
