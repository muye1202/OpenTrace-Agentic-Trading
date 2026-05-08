from __future__ import annotations

import json
import re
from typing import Any

from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

from tradingagents.agents.analysts.discovery_lane import merge_workbench_metrics, record_tool_call_links
from tradingagents.agents.analysts.tooling import build_tooling_state_update
from tradingagents.agents.analysts.workbench import (
    build_ledger_evidence_summary,
    build_minimum_evidence_question,
    build_workbench_metrics,
    build_workbench_prompt_block,
    normalize_ledger,
)
from tradingagents.agents.utils.agent_runtime.context_budget import build_report_evidence_summary
from tradingagents.agents.utils.llm.tool_binding import bind_tools_parallel_safe
from tradingagents.agents.utils.market_data.bundle_tools import get_catalyst_event_bundle
from tradingagents.dataflows.config import get_config
from tradingagents.schemas.catalyst_events import CatalystEventBundle, CatalystEventReport


def _extract_json_block(text: Any, start_tag: str, end_tag: str) -> dict[str, Any] | None:
    raw = str(text or "")
    pattern = rf"{re.escape(start_tag)}\s*(\{{.*?\}})\s*{re.escape(end_tag)}"
    match = re.search(pattern, raw, flags=re.DOTALL | re.IGNORECASE)
    candidates = [match.group(1)] if match else []
    stripped = raw.strip()
    if stripped.startswith("{") and stripped.endswith("}"):
        candidates.append(stripped)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except Exception:
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def _bundle_from_any(value: Any, ticker: str = "", as_of: str = "") -> dict[str, Any]:
    if isinstance(value, CatalystEventBundle):
        return value.to_dict()
    if isinstance(value, dict) and value:
        return CatalystEventBundle.from_dict(value).to_dict()
    if isinstance(value, str) and value.strip():
        try:
            return CatalystEventBundle.from_json(value).to_dict()
        except Exception:
            pass
    return CatalystEventBundle.from_dict({"ticker": ticker, "as_of": as_of}).to_dict()


def _latest_bundle_from_messages(messages: list[Any], ticker: str, as_of: str) -> dict[str, Any]:
    for msg in reversed(messages or []):
        content = getattr(msg, "content", None)
        if content is None and isinstance(msg, dict):
            content = msg.get("content")
        if not isinstance(content, str):
            continue
        try:
            parsed = json.loads(content)
        except Exception:
            continue
        if isinstance(parsed, dict) and (
            parsed.get("bundle") == "CatalystEventBundle" or "recent_events" in parsed
        ):
            return _bundle_from_any(parsed, ticker=ticker, as_of=as_of)
    return {}


def _fallback_report(bundle: dict[str, Any], reason: str = "") -> CatalystEventReport:
    normalized = CatalystEventBundle.from_dict(bundle).to_dict()
    recent = normalized.get("recent_events", []) or []
    upcoming = normalized.get("upcoming_events", []) or []
    filings = normalized.get("recent_filings", []) or []
    evidence = []
    for event in [*recent, *upcoming][:5]:
        evidence.append(
            {
                "source": event.get("source") or "event_bundle",
                "event_type": event.get("event_type") or "other",
                "date": event.get("event_time") or event.get("detected_at") or normalized.get("as_of", ""),
                "claim": event.get("title") or event.get("summary") or "Catalyst event in bundle.",
                "thesis_impact": "unknown",
                "confidence": event.get("confidence", 0.5),
                "url": event.get("url"),
            }
        )
    for filing in filings[:3]:
        evidence.append(
            {
                "source": filing.get("form_type") or "filing",
                "event_type": "sec_filing",
                "date": filing.get("filing_date") or normalized.get("as_of", ""),
                "claim": filing.get("filing_summary") or f"{filing.get('form_type', 'SEC filing')} filed.",
                "thesis_impact": "unknown",
                "confidence": filing.get("materiality_score", 0.5),
                "url": filing.get("primary_document_url"),
            }
        )

    max_materiality = 0.0
    scores = [event.get("materiality_score", 0.0) for event in recent + upcoming]
    scores += [filing.get("materiality_score", 0.0) for filing in filings]
    for score in scores:
        try:
            max_materiality = max(max_materiality, float(score))
        except Exception:
            pass
    rating = "HIGH" if max_materiality >= 0.75 else "MEDIUM" if max_materiality >= 0.45 else "LOW"
    rationale = reason or "Catalyst report was built from available structured events."
    return CatalystEventReport.from_dict(
        {
            "ticker": normalized.get("ticker", ""),
            "as_of": normalized.get("as_of", ""),
            "event_risk_rating": rating,
            "catalyst_score": max_materiality,
            "thesis_break_score": 0.0,
            "thesis_support_score": 0.0,
            "near_term_catalysts": [event.get("title", "") for event in upcoming if event.get("title")],
            "recent_material_events": [
                event.get("title", "") for event in recent if float(event.get("materiality_score") or 0.0) >= 0.45
            ],
            "thesis_supporting_events": [],
            "thesis_breaking_events": [],
            "unresolved_questions": ["Review event materiality manually if key source data is missing."],
            "recommended_action": "continue_analysis",
            "action_rationale": rationale,
            "risk_controls": ["Size conservatively around unresolved catalysts."],
            "evidence_table": evidence,
        }
    )


def parse_catalyst_report(content: Any, bundle: Any) -> dict[str, Any]:
    bundle_dict = _bundle_from_any(bundle)
    parsed = _extract_json_block(
        content,
        "BEGIN_CATALYST_EVENT_REPORT_JSON",
        "END_CATALYST_EVENT_REPORT_JSON",
    )
    if not parsed:
        return _fallback_report(bundle_dict, "Malformed catalyst analyst output; using validated fallback.").to_dict()
    parsed.setdefault("ticker", bundle_dict.get("ticker", ""))
    parsed.setdefault("as_of", bundle_dict.get("as_of", ""))
    return CatalystEventReport.from_dict(parsed).to_dict()


def format_catalyst_report_markdown(report: dict[str, Any]) -> str:
    lines = [
        "## Catalyst / Event-Risk Report",
        f"- Event risk rating: **{report.get('event_risk_rating', 'MEDIUM')}**",
        f"- Catalyst score: `{report.get('catalyst_score', 0.0)}`",
        f"- Thesis break score: `{report.get('thesis_break_score', 0.0)}`",
        f"- Thesis support score: `{report.get('thesis_support_score', 0.0)}`",
        f"- Recommended action: `{report.get('recommended_action', 'continue_analysis')}`",
        f"- Rationale: {report.get('action_rationale', '')}",
        "",
        "### Near-Term Catalysts",
        *[f"- {item}" for item in report.get("near_term_catalysts", []) or ["None identified."]],
        "",
        "### Recent Material Events",
        *[f"- {item}" for item in report.get("recent_material_events", []) or ["None identified."]],
        "",
        "### Thesis Impact",
        *[f"- Supporting: {item}" for item in report.get("thesis_supporting_events", [])],
        *[f"- Breaking: {item}" for item in report.get("thesis_breaking_events", [])],
        "",
        "### Risk Controls",
        *[f"- {item}" for item in report.get("risk_controls", []) or ["No extra controls."]],
        "",
        "| Source | Event type | Date | Thesis impact | Confidence | Claim |",
        "|---|---|---:|---|---:|---|",
    ]
    for item in report.get("evidence_table", []) or []:
        lines.append(
            "| {source} | {event_type} | {date} | {impact} | {confidence:.2f} | {claim} |".format(
                source=str(item.get("source", ""))[:80],
                event_type=str(item.get("event_type", ""))[:60],
                date=str(item.get("date", ""))[:40],
                impact=str(item.get("thesis_impact", ""))[:60],
                confidence=float(item.get("confidence", 0.0) or 0.0),
                claim=str(item.get("claim", "")).replace("|", "/")[:180],
            )
        )
    return "\n".join(lines).strip()


def _ledger_from_report(report: dict[str, Any]) -> dict[str, Any]:
    observations = []
    for idx, item in enumerate(report.get("evidence_table", [])[:8], 1):
        observations.append(
            {
                "id": f"obs_catalyst_{idx:03d}",
                "domain": "catalyst",
                "claim": item.get("claim", ""),
                "source_fact_ids": [],
                "surprise_score": item.get("confidence", 0.5),
                "why_it_matters": item.get("thesis_impact", "Event may affect thesis timing or risk."),
                "status": "explained",
            }
        )
    if not observations:
        observations.append(
            {
                "id": "obs_catalyst_001",
                "domain": "catalyst",
                "claim": report.get("action_rationale", "No material catalyst found."),
                "source_fact_ids": [],
                "surprise_score": report.get("catalyst_score", 0.0),
                "why_it_matters": "Catalyst context affects entry timing and risk budget.",
                "status": "explained",
            }
        )
    ledger = {
        "analyst_domain": "catalyst",
        "observations": observations,
        "active_hypotheses": [
            {
                "id": "h_catalyst_001",
                "claim": f"Catalyst risk is {report.get('event_risk_rating', 'MEDIUM')}",
                "origin": "anomaly_generated",
                "support": [obs["id"] for obs in observations[:3]],
                "against": [],
                "confidence": report.get("catalyst_score", 0.5),
                "falsifier": "New event data shows materially different timing or thesis impact.",
                "unresolved_questions": report.get("unresolved_questions", []),
            }
        ],
        "open_questions": report.get("unresolved_questions", []),
        "unexplained_but_decision_relevant": report.get("unresolved_questions", []),
    }
    return normalize_ledger("catalyst", ledger)


def create_catalyst_event_analyst(llm):
    def catalyst_event_analyst_node(state):
        if state.get("catalyst_report"):
            return {
                "catalyst_report": state["catalyst_report"],
                "catalyst_event_bundle": state.get("catalyst_event_bundle", {}),
                "catalyst_event_report_structured": state.get("catalyst_event_report_structured", {}),
            }

        current_date = state["trade_date"]
        ticker = state["company_of_interest"]
        bundle = _bundle_from_any(state.get("catalyst_event_bundle"), ticker=ticker, as_of=current_date)
        latest_tool_bundle = _latest_bundle_from_messages(state.get("messages", []), ticker, current_date)
        if latest_tool_bundle:
            bundle = latest_tool_bundle

        config = get_config()
        tool_round_cap = int(config.get("analyst_tool_round_cap", 2) or 2)
        global_tool_round_cap = int(config.get("max_tool_calls_total", 50) or 50)
        rounds = state.get("tool_round_counts") or state.get("tool_call_counts") or {}
        rounds_used = int(rounds.get("catalyst", 0) or 0)
        total_rounds_used = int(state.get("tool_call_total", sum(int(v or 0) for v in rounds.values())) or 0)
        force_no_tools = (
            state.get("force_no_tools_for") == "catalyst"
            or rounds_used >= tool_round_cap
            or total_rounds_used >= global_tool_round_cap
            or bool(latest_tool_bundle)
        )
        tools = [] if force_no_tools or state.get("catalyst_event_bundle") else [get_catalyst_event_bundle]
        selected_question = build_minimum_evidence_question(
            "catalyst", getattr(get_catalyst_event_bundle, "name", "get_catalyst_event_bundle")
        )

        system_message = f"""You are the Catalyst / Event-Risk Analyst in an agentic stock analysis system.

Your job is not to summarize all news. Identify discrete events that can change trade thesis, timing, or risk budget for {ticker}.

Input contract:
- You receive a CatalystEventBundle with recent events, upcoming catalysts, filings, macro placeholders, market context, optional position context, optional prior thesis, source quality, and freshness.

Output contract:
- Produce one JSON object between BEGIN_CATALYST_EVENT_REPORT_JSON and END_CATALYST_EVENT_REPORT_JSON.
- JSON fields: ticker, as_of, event_risk_rating, catalyst_score, thesis_break_score, thesis_support_score, near_term_catalysts, recent_material_events, thesis_supporting_events, thesis_breaking_events, unresolved_questions, recommended_action, action_rationale, risk_controls, evidence_table.
- event_risk_rating must be LOW, MEDIUM, HIGH, or CRITICAL.
- recommended_action must be one of: continue_analysis, rerun_full_analysis, risk_judge_review, freeze_new_buys, reduce_position, exit_review, watchlist_only, ignore_low_materiality.
- evidence_table rows require source, event_type, date, claim, thesis_impact, confidence, and url.

Current bundle:
{json.dumps(bundle, ensure_ascii=False)}

Use HIGH/CRITICAL only for discrete material events, near-term timing risk, likely thesis breaks, or severe position-aware risk. Prefer LOW/MEDIUM when evidence is sparse.
"""
        system_message += "\n\n---\nANALYST WORKBENCH DISCOVERY LANE:\n"
        system_message += build_workbench_prompt_block("catalyst", selected_question)

        prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    "You are a helpful AI assistant with access to tools: {tool_names}.\n{system_message}\n"
                    "For reference, current date is {current_date}; ticker is {ticker}.",
                ),
                MessagesPlaceholder(variable_name="messages"),
            ]
        )
        prompt = prompt.partial(system_message=system_message)
        prompt = prompt.partial(tool_names=", ".join([tool.name for tool in tools]))
        prompt = prompt.partial(current_date=current_date)
        prompt = prompt.partial(ticker=ticker)

        chain = prompt | (llm if not tools else bind_tools_parallel_safe(llm, tools))
        result = chain.invoke(state["messages"])
        tool_calls_count = len(getattr(result, "tool_calls", None) or [])
        tooling_state = build_tooling_state_update(state, "catalyst", tool_calls_count)
        tool_link_update = {}
        if tool_calls_count > 0:
            link_state = state
            for tool_call in getattr(result, "tool_calls", None) or []:
                tool_name = tool_call.get("name") if isinstance(tool_call, dict) else getattr(tool_call, "name", "")
                link_state = record_tool_call_links(
                    link_state, "catalyst", str(tool_name or ""), selected_question, tool_calls_count=1
                )
            tool_link_update = {
                "analyst_tool_call_links": link_state.get(
                    "analyst_tool_call_links", state.get("analyst_tool_call_links", {})
                )
            }

        report = ""
        structured_report = {}
        ledger = None
        evidence = ""
        workbench_metrics_update = {}
        if tool_calls_count == 0:
            structured_report = parse_catalyst_report(result.content, bundle)
            report = format_catalyst_report_markdown(structured_report)
            ledger = _ledger_from_report(structured_report)
            evidence = build_ledger_evidence_summary("catalyst", ledger) or build_report_evidence_summary(
                "catalyst", report
            )
            workbench_metrics_update = merge_workbench_metrics(
                {**state, **tool_link_update},
                "catalyst",
                build_workbench_metrics(ledger),
            )

        out = {
            "messages": [result],
            "catalyst_report": report,
            "catalyst_event_bundle": bundle,
            "catalyst_event_report_structured": structured_report,
            "catalyst_evidence": evidence,
            "force_no_tools_for": "",
            **tooling_state,
            **tool_link_update,
            **workbench_metrics_update,
        }
        if ledger is not None:
            out["catalyst_ledger"] = ledger
        return out

    return catalyst_event_analyst_node
