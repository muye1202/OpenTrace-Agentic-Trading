from __future__ import annotations

from typing import Any, Literal, TypedDict


EvidencePolarity = Literal["bullish", "bearish", "neutral", "mixed"]


class EvidenceLedgerItem(TypedDict, total=False):
    evidence_id: str
    ticker: str
    source_agent: str
    source_tool: str
    source_ref: str
    observed_at: str
    claim: str
    fact_type: str
    polarity: EvidencePolarity
    time_horizon: str
    confidence: float
    materiality: float
    supports: list[str]
    contradicts: list[str]
    raw_excerpt: str
    numeric_values: dict[str, float]
    source_node_id: str
    criticality: float


class EvidenceAdmissibilityReport(TypedDict):
    accepted_evidence_ids: list[str]
    downgraded_evidence: list[dict[str, str]]
    rejected_evidence: list[dict[str, str]]


_DOMAIN_CODES = {
    "market": "MKT",
    "sentiment": "SEN",
    "news": "NEW",
    "fundamentals": "FUN",
    "catalyst": "CAT",
}


def build_evidence_ledger(state: dict[str, Any] | None) -> list[EvidenceLedgerItem]:
    state = state or {}
    graph = state.get("evidence_graph") if isinstance(state.get("evidence_graph"), dict) else {}
    ticker = str(state.get("company_of_interest") or "").strip().upper()
    horizon = str(state.get("time_horizon") or "").strip()
    inference_by_fact = _inferences_by_fact(graph.get("inferences") or [])
    counters: dict[str, int] = {}
    items: list[EvidenceLedgerItem] = []

    for fact in graph.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        claim = str(fact.get("claim") or fact.get("text") or "").strip()
        source_ref = str(fact.get("id") or "").strip()
        if not claim or not source_ref:
            continue
        domain = str(fact.get("domain") or "market").strip().lower()
        code = _DOMAIN_CODES.get(domain, "MKT")
        counters[code] = counters.get(code, 0) + 1
        related = inference_by_fact.get(source_ref, [])
        polarity = _polarity(fact, related)
        item: EvidenceLedgerItem = {
            "evidence_id": f"E-{code}-{counters[code]:03d}",
            "ticker": ticker,
            "source_agent": f"{domain}_analyst",
            "source_tool": str(fact.get("source") or fact.get("section") or "").strip(),
            "source_ref": source_ref,
            "observed_at": _observed_at(fact, state),
            "claim": claim,
            "fact_type": _fact_type(domain, claim, fact),
            "polarity": polarity,
            "time_horizon": horizon,
            "confidence": _clamp01(fact.get("confidence"), 0.65),
            "materiality": _materiality(fact, related),
            "supports": _supports(polarity, claim, related),
            "contradicts": _contradicts(polarity, claim),
            "raw_excerpt": str(fact.get("text") or claim).strip()[:500],
            "numeric_values": _numeric_values(claim),
            "source_node_id": source_ref,
        }
        item["criticality"] = _criticality(item)
        items.append(item)
    return items


def validate_admissible_evidence(
    ledger: list[dict[str, Any]] | None,
    *,
    time_horizon: str = "",
) -> EvidenceAdmissibilityReport:
    accepted: list[str] = []
    downgraded: list[dict[str, str]] = []
    rejected: list[dict[str, str]] = []
    seen_refs: set[str] = set()

    for item in ledger or []:
        evidence_id = str(item.get("evidence_id") or "").strip()
        if not evidence_id:
            continue
        source_ref = str(item.get("source_ref") or "").strip()
        if not source_ref and not str(item.get("source_tool") or "").strip():
            rejected.append({"evidence_id": evidence_id, "reason": "missing source/tool reference"})
            continue
        if not str(item.get("observed_at") or "").strip():
            rejected.append({"evidence_id": evidence_id, "reason": "missing timestamp"})
            continue
        if source_ref in seen_refs:
            downgraded.append({"evidence_id": evidence_id, "reason": "duplicate source reference"})
            continue
        seen_refs.add(source_ref)
        if time_horizon and not str(item.get("time_horizon") or "").strip():
            downgraded.append({"evidence_id": evidence_id, "reason": "missing time horizon"})
            continue
        if not item.get("supports") and not item.get("contradicts"):
            downgraded.append({"evidence_id": evidence_id, "reason": "no decision implication"})
            continue
        accepted.append(evidence_id)

    return {
        "accepted_evidence_ids": accepted,
        "downgraded_evidence": downgraded,
        "rejected_evidence": rejected,
    }


def rank_critical_evidence(
    ledger: list[dict[str, Any]] | None,
    *,
    min_criticality: float = 0.45,
) -> list[EvidenceLedgerItem]:
    ranked: list[EvidenceLedgerItem] = []
    for item in ledger or []:
        normalized = dict(item)
        normalized["criticality"] = _criticality(item)
        if float(normalized["criticality"]) >= min_criticality:
            ranked.append(normalized)  # type: ignore[arg-type]
    return sorted(ranked, key=lambda item: float(item.get("criticality", 0.0)), reverse=True)


def _inferences_by_fact(inferences: Any) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = {}
    for inference in inferences if isinstance(inferences, list) else []:
        if not isinstance(inference, dict):
            continue
        for fact_id in inference.get("depends_on") or []:
            out.setdefault(str(fact_id), []).append(inference)
    return out


def _observed_at(fact: dict[str, Any], state: dict[str, Any]) -> str:
    raw = str(fact.get("as_of") or fact.get("observed_at") or "").strip()
    if raw:
        return raw
    return ""


def _polarity(fact: dict[str, Any], related: list[dict[str, Any]]) -> EvidencePolarity:
    stances = {str(item.get("stance") or "").strip().lower() for item in related}
    if "bearish" in stances and "bullish" in stances:
        return "mixed"
    if "bearish" in stances:
        return "bearish"
    if "bullish" in stances:
        return "bullish"
    text = str(fact.get("claim") or fact.get("text") or "").lower()
    if any(term in text for term in ("risk", "overbought", "unconfirmed", "weak", "below")):
        return "bearish"
    if any(term in text for term in ("breakout", "growth", "above", "upside", "strong")):
        return "bullish"
    return "neutral"


def _fact_type(domain: str, claim: str, fact: dict[str, Any]) -> str:
    section = str(fact.get("section") or "").strip().lower()
    text = f"{section} {claim}".lower()
    if domain == "market" and any(term in text for term in ("rsi", "atr", "technical", "volume")):
        return "technical_indicator"
    if domain == "news":
        return "news_event"
    if domain == "fundamentals":
        return "fundamental_metric"
    if domain == "catalyst":
        return "catalyst_event"
    return f"{domain}_fact"


def _materiality(fact: dict[str, Any], related: list[dict[str, Any]]) -> float:
    related_conf = [_clamp01(item.get("confidence"), 0.0) for item in related]
    base = max([_clamp01(fact.get("confidence"), 0.65), *related_conf])
    quality = str(fact.get("quality") or "").strip().lower()
    if quality in {"stale", "low_quality", "missing"}:
        base *= 0.55
    return round(min(1.0, max(0.1, base)), 3)


def _supports(polarity: str, claim: str, related: list[dict[str, Any]]) -> list[str]:
    text = " ".join([claim, *(str(item.get("claim") or "") for item in related)]).lower()
    supports: list[str] = []
    if polarity == "bullish":
        supports.append("supports_long_bias")
    if polarity in {"bearish", "mixed"}:
        supports.append("prefer_wait_for_trigger")
    if any(term in text for term in ("size", "concentration", "risk", "overbought")):
        supports.append("reduce_entry_aggression")
    if any(term in text for term in ("stop", "below", "invalid")):
        supports.append("tighten_invalidation")
    return list(dict.fromkeys(supports))


def _contradicts(polarity: str, claim: str) -> list[str]:
    text = claim.lower()
    out: list[str] = []
    if polarity in {"bearish", "mixed"}:
        out.append("act_now_market_buy")
    if "overbought" in text or "unconfirmed" in text:
        out.append("full_size_entry")
    return out


def _numeric_values(text: str) -> dict[str, float]:
    out: dict[str, float] = {}
    lower = text.lower()
    for label in ("rsi", "atr"):
        marker = lower.find(label)
        if marker < 0:
            continue
        tail = lower[marker : marker + 40]
        number = _first_number(tail)
        if number is not None:
            out[label] = number
    return out


def _first_number(text: str) -> float | None:
    import re

    match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _criticality(item: dict[str, Any]) -> float:
    materiality = _clamp01(item.get("materiality"), 0.5)
    confidence = _clamp01(item.get("confidence"), 0.5)
    source_quality = 1.0 if str(item.get("source_ref") or "").strip() else 0.4
    horizon_relevance = 1.0 if str(item.get("time_horizon") or "").strip() else 0.75
    decision_sensitivity = 1.0 if item.get("supports") or item.get("contradicts") else 0.45
    return round(materiality * confidence * source_quality * horizon_relevance * decision_sensitivity, 3)


def _clamp01(value: Any, default: float) -> float:
    try:
        number = float(value)
    except Exception:
        number = default
    return max(0.0, min(1.0, number))
