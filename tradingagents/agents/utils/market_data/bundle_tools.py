from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta
from typing import Annotated, Any, Dict

from langchain_core.tools import tool

from tradingagents.agents.utils.agent_runtime.agent_utils import (
    get_company_news_window,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_global_news,
    get_insider_sentiment,
    get_insider_transactions,
    get_news,
    get_recent_sec_filings,
)
from tradingagents.agents.utils.market_data.dark_pool_tools import (
    get_dark_pool_short_volume,
    get_off_exchange_volume_context,
)
from tradingagents.agents.utils.market_data.options_flow_tools import (
    get_options_sentiment_summary,
    get_unusual_options_activity,
)
from tradingagents.agents.utils.market_data.price_action_tools import get_price_action_summary
from tradingagents.agents.utils.market_data.short_interest_tools import (
    get_short_interest_data,
    get_squeeze_candidates_assessment,
)
from tradingagents.agents.utils.market_data.technical_indicators_tools import get_indicators
from tradingagents.agents.utils.market_data.vwap_tools import (
    get_intraday_vwap_position,
    get_multi_day_vwap_context,
)


async def _run_tool(tool_obj: Any, payload: Dict[str, Any]) -> str:
    try:
        return str(await tool_obj.ainvoke(payload))
    except Exception as e:
        return f"ToolError[{getattr(tool_obj, 'name', 'unknown')}]: {type(e).__name__}: {e}"


def select_bundle_first_tools(
    bundle_tool: Any,
    fallback_tools: list[Any],
    *,
    enable_bundle_tools: bool,
    rounds_used: int,
) -> list[Any]:
    """Expose only the bundle on the first analyst round, then fall back if needed."""
    if not enable_bundle_tools:
        return list(fallback_tools)
    if int(rounds_used or 0) <= 0:
        return [bundle_tool]
    return list(fallback_tools)


def _score_bundle_line(line: str) -> int:
    lower = line.lower()
    score = 0
    if re.search(r"\$?\d+(?:\.\d+)?%?", line):
        score += 2
    for term in (
        "last close",
        "returns",
        "atr",
        "volume",
        "support",
        "resistance",
        "trigger",
        "risk",
        "sentiment",
        "earnings",
        "revenue",
        "margin",
        "cash",
        "debt",
        "insider",
        "short",
        "vwap",
        "options",
        "valuation",
        "price",
    ):
        if term in lower:
            score += 1
    if line.lstrip().startswith(("-", "*", "|")):
        score += 1
    return score


def _bundle_domain(bundle_name: str) -> str:
    lower = str(bundle_name or "").lower()
    if "fundamental" in lower:
        return "fundamentals"
    if "news" in lower:
        return "news"
    if "sentiment" in lower:
        return "sentiment"
    return "market"


def _clean_fact_part(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9_]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "unknown"


def _first_json_object(raw: Any) -> Any:
    if isinstance(raw, (dict, list)):
        return raw
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def _compact_source_quality(results: Dict[str, Any]) -> dict[str, Any]:
    quality: dict[str, Any] = {}
    for section, raw in results.items():
        text = str(raw or "")
        missing = _missing_summary(section, text)
        quality[section] = {
            "status": "missing" if missing else "ok",
            "chars": len(text),
            "issue": missing or "",
        }
    return quality


def _event_from_line(
    *,
    ticker: str,
    source: str,
    line: str,
    event_type: str,
    as_of: str,
    idx: int,
    materiality_score: float,
) -> dict[str, Any]:
    title = re.sub(r"\s+", " ", str(line or "")).strip("-* |")
    return {
        "event_id": f"{source}_{idx:03d}",
        "ticker": ticker,
        "event_type": event_type,
        "event_time": None,
        "detected_at": as_of,
        "source": source,
        "title": title[:220] or f"{source} event",
        "summary": title[:500],
        "url": None,
        "materiality_score": materiality_score,
        "novelty_score": 0.5,
        "sentiment_score": None,
        "confidence": 0.6,
    }


def _events_from_text(ticker: str, source: str, raw: Any, as_of: str, limit: int = 8) -> list[dict[str, Any]]:
    text = str(raw or "")
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    selected = []
    for line in lines:
        lower = line.lower()
        if len(line) < 18:
            continue
        if any(
            term in lower
            for term in (
                "earnings",
                "guidance",
                "filing",
                "sec",
                "offering",
                "insider",
                "lawsuit",
                "regulatory",
                "contract",
                "launch",
                "dividend",
                "split",
                "rating",
                "upgrade",
                "downgrade",
                "volume",
                "price",
            )
        ):
            selected.append(line)
        if len(selected) >= limit:
            break
    return [
        _event_from_line(
            ticker=ticker,
            source=source,
            line=line,
            event_type="price_volume_shock" if source == "price_action_summary" else "other",
            as_of=as_of,
            idx=idx,
            materiality_score=0.55 if source == "price_action_summary" else 0.45,
        )
        for idx, line in enumerate(selected, 1)
    ]


def _filings_from_raw(raw: Any, as_of: str) -> list[dict[str, Any]]:
    parsed = _first_json_object(raw)
    candidates: list[Any] = []
    if isinstance(parsed, list):
        candidates = parsed
    elif isinstance(parsed, dict):
        for key in ("filings", "recent_filings", "data", "items"):
            if isinstance(parsed.get(key), list):
                candidates = parsed[key]
                break
        if not candidates and any(k in parsed for k in ("form_type", "form", "accession_number")):
            candidates = [parsed]
    filings = []
    for idx, item in enumerate([x for x in candidates if isinstance(x, dict)][:10], 1):
        form = str(item.get("form_type") or item.get("form") or item.get("type") or "").upper()
        url = item.get("primary_document_url") or item.get("url") or item.get("link") or ""
        filings.append(
            {
                "accession_number": str(item.get("accession_number") or item.get("accessionNo") or f"filing_{idx:03d}"),
                "cik": str(item.get("cik") or ""),
                "form_type": form or "SEC",
                "filing_date": str(item.get("filing_date") or item.get("date") or as_of),
                "report_date": item.get("report_date"),
                "primary_document_url": str(url or ""),
                "filing_summary": str(item.get("filing_summary") or item.get("summary") or item.get("description") or ""),
                "extracted_signals": [],
                "materiality_score": 0.75 if form in {"8-K", "10-Q", "10-K", "S-3", "424B"} else 0.5,
            }
        )
    if filings:
        return filings
    text = str(raw or "")
    out = []
    for idx, line in enumerate([line.strip() for line in text.splitlines() if line.strip()][:10], 1):
        if not re.search(r"\b(10-K|10-Q|8-K|S-1|S-3|424B|DEF 14A|13D|13G|Form 4|6-K|20-F)\b", line, re.I):
            continue
        match = re.search(r"\b(10-K|10-Q|8-K|S-1|S-3|424B|DEF 14A|13D|13G|Form 4|6-K|20-F)\b", line, re.I)
        form = match.group(1).upper() if match else "SEC"
        out.append(
            {
                "accession_number": f"text_filing_{idx:03d}",
                "cik": "",
                "form_type": form,
                "filing_date": as_of,
                "report_date": None,
                "primary_document_url": "",
                "filing_summary": line[:500],
                "extracted_signals": [],
                "materiality_score": 0.75 if form in {"8-K", "10-Q", "10-K", "S-3", "424B"} else 0.5,
            }
        )
    return out


def _missing_summary(section: str, value: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return "empty output"
    lower = text.lower()
    if lower.startswith("toolerror"):
        return text[:240]
    for marker in ("no ", "not available", "failed", "error", "missing", "n/a", "nan"):
        if marker in lower:
            return text.splitlines()[0][:240]
    return None


def format_evidence_bundle(
    bundle_name: str,
    symbol: str,
    curr_date: str,
    results: Dict[str, Any],
    *,
    max_chars: int = 6000,
) -> str:
    """Return a compact JSON evidence packet instead of raw concatenated tool output."""
    domain = _bundle_domain(bundle_name)
    facts: list[dict[str, Any]] = []
    missing_data: list[dict[str, str]] = []
    source_quality: list[dict[str, Any]] = []
    section_counts: dict[str, int] = {}

    for section, raw in results.items():
        text = str(raw or "")
        if missing := _missing_summary(section, text):
            missing_data.append({"section": section, "issue": missing})
        source_quality.append({"section": section, "chars": len(text), "status": "missing" if missing else "ok"})

        lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
        scored = [
            (_score_bundle_line(line), idx, line)
            for idx, line in enumerate(lines)
            if line and not line.startswith("##")
        ]
        selected = [
            line
            for score, _, line in sorted(scored, key=lambda item: (-item[0], item[1]))
            if score > 0
        ][:4]
        for line in selected:
            section_counts[section] = section_counts.get(section, 0) + 1
            fact_text = line[:320]
            facts.append(
                {
                    "id": f"fact_{domain}_{_clean_fact_part(section)}_{section_counts[section]:03d}",
                    "domain": domain,
                    "claim": fact_text,
                    "text": fact_text,
                    "source": section,
                    "section": section,
                    "as_of": curr_date,
                    "confidence": 0.85,
                    "quality": "normal",
                    "source_type": "vendor",
                }
            )

    packet: dict[str, Any] = {
        "bundle": bundle_name,
        "symbol": symbol,
        "date": curr_date,
        "facts": facts[:28],
        "missing_data": missing_data[:12],
        "source_quality": source_quality,
        "instruction": "Use this compact evidence packet for analysis; do not treat omitted raw rows as absent data.",
    }

    text = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    if len(text) <= max_chars:
        return text

    packet["facts"] = packet["facts"][: max(6, len(packet["facts"]) // 2)]
    packet["source_quality"] = packet["source_quality"][:12]
    text = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    while len(text) > max_chars and packet["facts"]:
        packet["facts"].pop()
        text = json.dumps(packet, ensure_ascii=False, separators=(",", ":"))
    return text[:max_chars]


def _parse_indicator_csv(indicators_csv: str) -> list[str]:
    allowed = [
        "close_50_sma",
        "close_200_sma",
        "close_10_ema",
        "macd",
        "macds",
        "macdh",
        "rsi",
        "boll",
        "boll_ub",
        "boll_lb",
        "atr",
        "vwma",
        "mfi",
    ]
    requested = [x.strip() for x in str(indicators_csv or "").split(",") if x.strip()]
    if not requested:
        requested = ["close_10_ema", "close_50_sma", "macd", "rsi", "atr"]

    filtered: list[str] = []
    for indicator in requested:
        if indicator in allowed and indicator not in filtered:
            filtered.append(indicator)
        if len(filtered) >= 6:
            break
    return filtered or ["close_10_ema", "close_50_sma", "macd", "rsi", "atr"]


@tool
async def get_market_data_bundle(
    symbol: Annotated[str, "Ticker symbol, e.g. AAPL"],
    curr_date: Annotated[str, "Current trading date in YYYY-mm-dd format"],
    indicators_csv: Annotated[
        str,
        "Comma-separated indicator names (max 6). Example: close_10_ema,close_50_sma,macd,rsi,atr",
    ] = "close_10_ema,close_50_sma,macd,rsi,atr",
    indicator_look_back_days: Annotated[int, "Look-back window for indicators"] = 90,
) -> str:
    """
    Fetch market analyst data in a single bundled tool call.
    Runs all sub-tools concurrently to reduce extra LLM planning turns.
    """
    indicators = _parse_indicator_csv(indicators_csv)
    tasks: dict[str, asyncio.Task] = {
        "price_action_summary": asyncio.create_task(
            _run_tool(
                get_price_action_summary,
                {"symbol": symbol, "curr_date": curr_date, "look_back_days": 180},
            )
        ),
        "intraday_vwap_position": asyncio.create_task(
            _run_tool(get_intraday_vwap_position, {"symbol": symbol, "curr_date": curr_date})
        ),
        "multi_day_vwap_context": asyncio.create_task(
            _run_tool(get_multi_day_vwap_context, {"symbol": symbol, "curr_date": curr_date})
        ),
        "unusual_options_activity": asyncio.create_task(
            _run_tool(get_unusual_options_activity, {"symbol": symbol, "curr_date": curr_date})
        ),
        "options_sentiment_summary": asyncio.create_task(
            _run_tool(get_options_sentiment_summary, {"symbol": symbol, "curr_date": curr_date})
        ),
        "dark_pool_short_volume": asyncio.create_task(
            _run_tool(get_dark_pool_short_volume, {"symbol": symbol, "curr_date": curr_date})
        ),
        "off_exchange_volume_context": asyncio.create_task(
            _run_tool(get_off_exchange_volume_context, {"symbol": symbol, "curr_date": curr_date})
        ),
        "short_interest_data": asyncio.create_task(
            _run_tool(get_short_interest_data, {"symbol": symbol, "curr_date": curr_date})
        ),
        "squeeze_candidates_assessment": asyncio.create_task(
            _run_tool(get_squeeze_candidates_assessment, {"symbol": symbol, "curr_date": curr_date})
        ),
    }

    for indicator in indicators:
        tasks[f"indicator::{indicator}"] = asyncio.create_task(
            _run_tool(
                get_indicators,
                {
                    "symbol": symbol,
                    "indicator": indicator,
                    "curr_date": curr_date,
                    "look_back_days": int(indicator_look_back_days),
                },
            )
        )

    results = {key: await task for key, task in tasks.items()}
    return format_evidence_bundle("Market Data Bundle", symbol, curr_date, results)


@tool
async def get_fundamentals_data_bundle(
    ticker: Annotated[str, "Ticker symbol"],
    curr_date: Annotated[str, "Current trading date in YYYY-mm-dd format"],
    freq: Annotated[str, "Statement frequency (quarterly or annual)"] = "quarterly",
) -> str:
    """Fetch fundamentals analyst data in a single bundled tool call."""
    tasks = {
        "fundamentals": asyncio.create_task(
            _run_tool(get_fundamentals, {"ticker": ticker, "curr_date": curr_date})
        ),
        "income_statement": asyncio.create_task(
            _run_tool(
                get_income_statement,
                {"ticker": ticker, "freq": freq, "curr_date": curr_date},
            )
        ),
        "balance_sheet": asyncio.create_task(
            _run_tool(
                get_balance_sheet,
                {"ticker": ticker, "freq": freq, "curr_date": curr_date},
            )
        ),
        "cashflow": asyncio.create_task(
            _run_tool(get_cashflow, {"ticker": ticker, "freq": freq, "curr_date": curr_date})
        ),
        "insider_transactions": asyncio.create_task(
            _run_tool(get_insider_transactions, {"ticker": ticker, "curr_date": curr_date})
        ),
        "insider_sentiment": asyncio.create_task(
            _run_tool(get_insider_sentiment, {"ticker": ticker, "curr_date": curr_date})
        ),
    }
    results = {key: await task for key, task in tasks.items()}
    return format_evidence_bundle("Fundamentals Data Bundle", ticker, curr_date, results)


@tool
async def get_news_data_bundle(
    ticker: Annotated[str, "Ticker symbol"],
    curr_date: Annotated[str, "Current trading date in YYYY-mm-dd format"],
    company_look_back_days: Annotated[int, "Company-news look-back days"] = 14,
    global_look_back_days: Annotated[int, "Global-news look-back days"] = 5,
    global_limit: Annotated[int, "Max global headlines"] = 10,
) -> str:
    """Fetch news analyst data in a single bundled tool call."""
    try:
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_date = (curr_dt - timedelta(days=int(company_look_back_days))).strftime("%Y-%m-%d")
    except Exception:
        start_date = curr_date

    tasks = {
        "company_news_window": asyncio.create_task(
            _run_tool(
                get_company_news_window,
                {"ticker": ticker, "curr_date": curr_date, "look_back_days": int(company_look_back_days)},
            )
        ),
        "company_news_raw": asyncio.create_task(
            _run_tool(get_news, {"ticker": ticker, "start_date": start_date, "end_date": curr_date})
        ),
        "global_news": asyncio.create_task(
            _run_tool(
                get_global_news,
                {
                    "curr_date": curr_date,
                    "look_back_days": int(global_look_back_days),
                    "limit": int(global_limit),
                },
            )
        ),
    }
    results = {key: await task for key, task in tasks.items()}
    return format_evidence_bundle("News Data Bundle", ticker, curr_date, results)


@tool
async def get_catalyst_event_bundle(
    ticker: Annotated[str, "Ticker symbol"],
    curr_date: Annotated[str, "Current trading date in YYYY-mm-dd format"],
    portfolio_context: Annotated[str, "Optional current portfolio context"] = "",
    company_look_back_days: Annotated[int, "Company-news look-back days"] = 14,
) -> str:
    """Build the structured CatalystEventBundle used by the catalyst analyst."""
    try:
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_date = (curr_dt - timedelta(days=int(company_look_back_days))).strftime("%Y-%m-%d")
    except Exception:
        start_date = curr_date

    tasks = {
        "company_news_window": asyncio.create_task(
            _run_tool(
                get_company_news_window,
                {"ticker": ticker, "curr_date": curr_date, "look_back_days": int(company_look_back_days)},
            )
        ),
        "company_news_raw": asyncio.create_task(
            _run_tool(get_news, {"ticker": ticker, "start_date": start_date, "end_date": curr_date})
        ),
        "recent_sec_filings": asyncio.create_task(
            _run_tool(get_recent_sec_filings, {"ticker": ticker, "curr_date": curr_date})
        ),
        "insider_transactions": asyncio.create_task(
            _run_tool(get_insider_transactions, {"ticker": ticker, "curr_date": curr_date})
        ),
        "price_action_summary": asyncio.create_task(
            _run_tool(get_price_action_summary, {"symbol": ticker, "curr_date": curr_date, "look_back_days": 90})
        ),
    }
    results = {key: await task for key, task in tasks.items()}
    recent_events: list[dict[str, Any]] = []
    recent_events.extend(_events_from_text(ticker, "company_news_window", results["company_news_window"], curr_date))
    recent_events.extend(_events_from_text(ticker, "company_news_raw", results["company_news_raw"], curr_date))
    recent_events.extend(_events_from_text(ticker, "insider_transactions", results["insider_transactions"], curr_date))
    recent_events.extend(_events_from_text(ticker, "price_action_summary", results["price_action_summary"], curr_date, limit=4))
    filings = _filings_from_raw(results["recent_sec_filings"], curr_date)
    for idx, filing in enumerate(filings[:5], 1):
        recent_events.append(
            {
                "event_id": f"filing_{idx:03d}",
                "ticker": ticker,
                "event_type": "sec_filing",
                "event_time": filing.get("filing_date"),
                "detected_at": curr_date,
                "source": "recent_sec_filings",
                "title": f"{filing.get('form_type', 'SEC filing')} filed",
                "summary": filing.get("filing_summary") or "",
                "url": filing.get("primary_document_url") or None,
                "materiality_score": filing.get("materiality_score", 0.5),
                "novelty_score": 0.6,
                "sentiment_score": None,
                "confidence": 0.75,
            }
        )

    price_text = str(results.get("price_action_summary") or "")
    shock = bool(re.search(r"\b(gap|breakout|breakdown|volume|shock|spike|plunge)\b", price_text, re.I))
    bundle = {
        "bundle": "CatalystEventBundle",
        "ticker": ticker,
        "company_name": None,
        "as_of": curr_date,
        "recent_events": recent_events[:20],
        "upcoming_events": [],
        "recent_filings": filings[:10],
        "macro_events": [],
        "market_context": {
            "last_close": None,
            "one_day_return_pct": None,
            "five_day_return_pct": None,
            "volume_ratio": None,
            "price_volume_shock": shock,
            "summary": price_text[:1000],
        },
        "position_context": {
            "has_position": bool(str(portfolio_context or "").strip()),
            "position_size_pct": None,
            "cost_basis": None,
            "unrealized_pnl_pct": None,
            "stop_loss": None,
            "target_price": None,
            "max_position_size_pct": None,
            "holding_period": None,
        }
        if str(portfolio_context or "").strip()
        else None,
        "prior_thesis": None,
        "source_quality": _compact_source_quality(results),
        "data_freshness": {key: curr_date for key in results},
    }
    return json.dumps(bundle, ensure_ascii=False, separators=(",", ":"))


@tool
async def get_sentiment_data_bundle(
    ticker: Annotated[str, "Ticker symbol"],
    curr_date: Annotated[str, "Current trading date in YYYY-mm-dd format"],
    look_back_days: Annotated[int, "Look-back days for sentiment proxy"] = 21,
) -> str:
    """Fetch sentiment analyst data in a single bundled tool call."""
    try:
        curr_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_date = (curr_dt - timedelta(days=int(look_back_days))).strftime("%Y-%m-%d")
    except Exception:
        start_date = curr_date

    tasks = {
        "company_news_window": asyncio.create_task(
            _run_tool(
                get_company_news_window,
                {"ticker": ticker, "curr_date": curr_date, "look_back_days": int(look_back_days)},
            )
        ),
        "company_news_raw": asyncio.create_task(
            _run_tool(get_news, {"ticker": ticker, "start_date": start_date, "end_date": curr_date})
        ),
    }
    results = {key: await task for key, task in tasks.items()}
    return format_evidence_bundle("Sentiment Data Bundle", ticker, curr_date, results)
