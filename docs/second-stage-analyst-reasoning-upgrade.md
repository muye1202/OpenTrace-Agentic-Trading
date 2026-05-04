# Second-Stage Analyst Reasoning Upgrade Spec

## Purpose

Upgrade the analyst pipeline from report generation over large vendor payloads into a structured reasoning system that maximizes each analyst's judgment. The core shift is to stop treating long Markdown reports as the primary intelligence artifact. Analysts should reason over compact evidence, maintain explicit hypotheses, expose uncertainty, and emit structured inferences that downstream agents can audit.

This stage builds on the first upgrade, which introduced compact evidence bundles and downstream evidence summaries.

## Design Principles

- **Reason over discriminating evidence, not raw data.**
- **Externalize intermediate reasoning into structured state.**
- **Separate evidence, inference, debate, and presentation.**
- **Make every decision traceable back to source facts.**
- **Let models spend context on judgment, not vendor payload digestion.**

## Upgrade 1: Analyst Workbench

### Summary

Replace each analyst's current "fetch data, write report" workflow with a hypothesis-driven research runtime.

Each analyst should maintain a compact hypothesis ledger:

```json
{
  "active_hypotheses": [
    {
      "claim": "Trend continuation remains dominant",
      "support": ["price above 10 EMA and 50 SMA", "breakout near 20D high"],
      "against": ["RSI overbought", "ATR elevated"],
      "confidence": 0.62,
      "falsifier": "close below 10 EMA on high volume"
    }
  ],
  "resolved_questions": [],
  "open_questions": [],
  "do_not_fetch_again": []
}
```

### Runtime Loop

1. **Initialize competing hypotheses**
   - Market: continuation, exhaustion, range, event dislocation.
   - Fundamentals: structural inflection, cyclical peak, valuation stretch, data insufficient.
   - News: catalyst continuation, sell-the-news, macro drag, no material catalyst.
   - Sentiment: attention acceleration, crowded trade, narrative fatigue, low-signal noise.

2. **Request only discriminating evidence**
   - Tool calls must answer a specific open question.
   - Re-fetching data already represented in the ledger is blocked.
   - Missing current-day data should use prior valid trading-day observations when appropriate.

3. **Update the hypothesis ledger**
   - Add support and counter-evidence.
   - Adjust confidence.
   - Record falsifiers and uncertainty.

4. **Run a critic pass**
   - Identify unsupported claims.
   - Flag stale data.
   - Flag price-anchor conflicts.
   - Ask what would change the analyst's conclusion.

5. **Emit final analyst artifacts**
   - Structured ledger.
   - Structured domain inference.
   - Human-readable memo for UI display.

### Expected Benefits

- Less metric inventory.
- More explicit tradeoffs.
- Better falsifiability.
- Fewer redundant tool calls.
- Stronger downstream debate because claims include support, counter-evidence, and confidence.

## Upgrade 2: Evidence Graph

### Summary

Introduce a shared typed evidence graph as the central intelligence artifact. Reports become display output, not reasoning input.

Current flow:

```text
vendor data -> analyst reports -> bull/bear debate -> manager -> trader -> risk judge
```

Target flow:

```text
vendor facts -> evidence graph -> analyst ledgers -> thesis graph -> debate -> decision
```

### Core Schema

```json
{
  "facts": [
    {
      "id": "price_001",
      "domain": "market",
      "claim": "SNDK closed at 1240.02 after a 76.7% 1M gain",
      "source": "price_action_summary",
      "as_of": "2026-05-05",
      "confidence": 0.95
    }
  ],
  "inferences": [
    {
      "id": "market_inf_001",
      "claim": "Trend is strong but overextended",
      "depends_on": ["price_001", "rsi_001", "atr_001"],
      "analyst": "market",
      "confidence": 0.72
    }
  ],
  "conflicts": [
    {
      "claim_a": "buy breakout",
      "claim_b": "wait for pullback",
      "reason": "same trend evidence, different risk/reward interpretation"
    }
  ]
}
```

### Agent Responsibilities

| Component | Responsibility |
|---|---|
| Bundle tools | Emit compact source facts and data quality metadata. |
| Evidence auditor | Detect stale data, price conflicts, missing sections, unsupported claims. |
| Analysts | Convert facts into domain-specific inferences and falsifiers. |
| Bull/Bear researchers | Debate thesis strength using evidence graph projections. |
| Research manager | Select the best thesis based on evidence quality and decision relevance. |
| Trader | Convert thesis into executable or conditional plan. |
| Risk judge | Validate execution risk, portfolio fit, and weakest assumptions. |

### Evidence Projections

Downstream agents should not consume the entire graph. Each node receives a projection:

- **Bull researcher:** top bullish inferences, counter-evidence, unresolved conflicts.
- **Bear researcher:** top bearish inferences, weak assumptions, stale or missing data.
- **Trader:** chosen thesis, levels, invalidation, sizing constraints.
- **Risk judge:** execution plan, weakest evidence, portfolio exposure, risk asymmetry.

## Recommended Sequence

### Phase 1: Analyst Workbench

Implement first because it directly improves analyst reasoning.

Deliverables:

- `AnalystHypothesis` schema.
- `AnalystLedger` schema.
- analyst ledger state keys:
  - `market_ledger`
  - `sentiment_ledger`
  - `news_ledger`
  - `fundamentals_ledger`
- critic pass helper.
- report writer that uses ledger, not raw tool history.

Acceptance criteria:

- Analyst reports include support, counter-evidence, falsifier, confidence.
- Analyst reports avoid executable BUY/HOLD/SELL proposals.
- Tool calls are tied to open questions.
- No fallback call is allowed unless it resolves a named open question.

### Phase 2: Evidence Graph

Implement after ledgers exist.

Deliverables:

- `EvidenceFact`, `EvidenceInference`, `EvidenceConflict`, `EvidenceGraph` schemas.
- deterministic evidence auditor.
- graph projection helpers for each downstream agent.
- trace output for final decisions.

Acceptance criteria:

- Final decision can be traced:

```text
decision -> thesis -> inference -> facts -> sources
```

- Risk judge cites evidence quality and weakest assumptions.
- Debate agents consume graph projections rather than full reports.
- UI can display the decision trace.

## Evaluation Plan

Use `trading_history.db` replay first, avoiding new vendor calls.

Metrics:

- total tool calls
- total tool-result characters
- analyst report length
- count of explicit falsifiers
- count of claims linked to evidence
- final decision trace completeness
- analyst proposal leakage
- stale or conflicting price references

Regression targets:

- Reduce raw tool-result chars by another 50% from current compact-bundle workflow.
- Preserve or increase concrete decision evidence count.
- Every analyst emits at least one falsifier.
- Every final decision cites the weakest assumption.

## Strategic Goal

The target system should no longer be "LLM writes reports from market data." It should be a reasoning pipeline where agents:

1. gather only discriminating evidence,
2. maintain explicit hypotheses,
3. expose uncertainty,
4. debate structured inferences,
5. produce auditable decisions.

That is the architectural line where analyst capability improves structurally rather than by adding more prompt text or larger context windows.
