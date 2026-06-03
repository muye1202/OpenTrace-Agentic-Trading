from __future__ import annotations

from typing import Any, TypedDict


ALLOWED_DECISION_FIELDS = {
    "action",
    "execution_mode",
    "order_type",
    "entry_price",
    "entry_condition",
    "stop_loss",
    "take_profit",
    "position_size_pct",
    "max_loss_pct",
    "trigger_condition",
    "time_horizon",
    "invalidation_condition",
}

EXECUTABLE_TRADER_FIELDS = {
    "action",
    "execution_mode",
    "order_type",
    "position_size_pct",
    "entry_condition",
    "stop_loss",
    "take_profit",
}


class ResearchDebateValidation(TypedDict):
    accepted_turns: list[dict[str, Any]]
    rejected_turns: list[dict[str, Any]]


class TraderPlanValidation(TypedDict):
    valid: bool
    violations: list[str]


def validate_research_debate_turns(
    turns: list[dict[str, Any]] | None,
    *,
    evidence_ids: list[str] | set[str],
    active_issue_ids: list[str] | set[str],
) -> ResearchDebateValidation:
    valid_evidence = {str(item) for item in evidence_ids}
    valid_issues = {str(item) for item in active_issue_ids}
    accepted: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []

    for raw in turns or []:
        turn = dict(raw or {})
        reason = _research_turn_rejection_reason(turn, valid_evidence, valid_issues)
        if reason:
            rejected.append({"turn": turn, "reason": reason})
        else:
            accepted.append(turn)
    return {"accepted_turns": accepted, "rejected_turns": rejected}


def validate_trader_plan(
    plan: dict[str, Any] | None,
    *,
    evidence_ids: list[str] | set[str],
    thesis_ids: list[str] | set[str],
) -> TraderPlanValidation:
    if not isinstance(plan, dict):
        return {"valid": False, "violations": ["plan must be an object"]}

    valid_refs = {str(item) for item in evidence_ids} | {str(item) for item in thesis_ids}
    valid_refs.update({"recommended_plan_constraints", "execution_plan_compiler", "trader_self_audit"})
    links = plan.get("rationale_links")
    violations: list[str] = []
    if not isinstance(links, dict):
        return {"valid": False, "violations": ["rationale_links must be an object"]}

    execution_mode = str(plan.get("execution_mode") or "").strip()
    if execution_mode not in {"act_now", "wait_for_trigger"}:
        violations.append("execution_mode must be act_now or wait_for_trigger")

    for field in sorted(EXECUTABLE_TRADER_FIELDS):
        if field not in plan:
            continue
        refs = links.get(field)
        if not isinstance(refs, list) or not refs:
            violations.append(f"{field} missing rationale_links")
            continue
        invalid = [str(ref) for ref in refs if str(ref) not in valid_refs and not str(ref).startswith(("C-", "I-"))]
        if invalid:
            violations.append(f"{field} has invalid rationale links: {', '.join(invalid)}")

    return {"valid": not violations, "violations": violations}


def _research_turn_rejection_reason(
    turn: dict[str, Any],
    valid_evidence: set[str],
    valid_issues: set[str],
) -> str:
    evidence_ids = [str(item) for item in turn.get("evidence_ids") or [] if str(item)]
    if not evidence_ids:
        return "missing evidence_ids"
    missing = [item for item in evidence_ids if item not in valid_evidence]
    if missing:
        return f"unknown evidence_ids: {', '.join(missing)}"
    issue_id = str(turn.get("issue_id") or "").strip()
    if issue_id not in valid_issues:
        return "unknown issue_id"
    implication = turn.get("plan_implication")
    if not isinstance(implication, dict):
        return "missing plan_implication"
    field = str(implication.get("field") or "").strip()
    if field not in ALLOWED_DECISION_FIELDS:
        return "invalid plan_implication.field"
    if "proposed_value" not in implication:
        return "missing plan_implication.proposed_value"
    if not str(turn.get("claim") or "").strip():
        return "missing claim"
    return ""
