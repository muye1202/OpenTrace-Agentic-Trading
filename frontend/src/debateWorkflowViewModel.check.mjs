import assert from 'node:assert/strict';

import {
  buildDebateWorkflowViewModel,
  splitDebateHistory,
} from './debateWorkflowViewModel.js';

const reports = {
  investment_debate_state: {
    count: 2,
    history: [
      'Bull Analyst: Revenue acceleration and margin expansion support a tactical BUY.',
      'Bear Analyst: Valuation and post-earnings reversal risk argue for patience.',
    ].join('\n'),
    bull_history: 'Bull Analyst: Revenue acceleration and margin expansion support a tactical BUY.',
    bear_history: 'Bear Analyst: Valuation and post-earnings reversal risk argue for patience.',
    judge_decision: 'Research Manager: BUY, but only with sizing discipline and catalyst confirmation.',
  },
  trader_investment_plan: [
    'FINAL TRANSACTION PROPOSAL',
    'ACTION: BUY',
    'POSITION_SIZE_PCT: 12',
    'EXECUTION_INTENT: ACT_NOW',
    'STOP_LOSS: 84.5',
  ].join('\n'),
  risk_debate_state: {
    count: 3,
    history: [
      'Risky Analyst: Act now before momentum reprices the upside.',
      'Safe Analyst: Reduce sizing because support is still unconfirmed.',
      'Neutral Analyst: Wait for confirmation and keep upside optionality.',
    ].join('\n'),
    risky_history: 'Risky Analyst: Act now before momentum reprices the upside.',
    safe_history: 'Safe Analyst: Reduce sizing because support is still unconfirmed.',
    neutral_history: 'Neutral Analyst: Wait for confirmation and keep upside optionality.',
    judge_decision: 'Risk Manager: HOLD until trigger, reduce risk, and use a tighter stop.',
  },
  final_trade_decision: [
    'Final decision: preserve capital.',
    'BEGIN_DECISION_JSON {"action":"HOLD","ticker":"INTC","position_size_pct":null,"stop_loss":84.5,"take_profit":115,"execution_intent":"wait_for_trigger","rationale":"Risk debate shifted the proposal from immediate action to conditional confirmation."} END_DECISION_JSON',
  ].join('\n'),
};

const turns = splitDebateHistory(reports.risk_debate_state.history);
assert.equal(turns.length, 3);
assert.equal(turns[0].speaker, 'Risky Analyst');
assert.match(turns[1].content, /Reduce sizing/);

const viewModel = buildDebateWorkflowViewModel(reports);

assert.equal(viewModel.hasDebate, true);
assert.equal(viewModel.workflowSteps.length, 7);
assert.equal(viewModel.researchArena.participants.length, 2);
assert.equal(viewModel.researchArena.judge.role, 'Research Manager');
assert.equal(viewModel.riskArena.participants.length, 3);
assert.equal(viewModel.riskArena.judge.role, 'Risk Manager');
assert.equal(viewModel.summary.researchTurns, 2);
assert.equal(viewModel.summary.riskTurns, 3);

assert.equal(viewModel.traderProposal.action, 'BUY');
assert.equal(viewModel.traderProposal.executionIntent, 'ACT_NOW');
assert.equal(viewModel.finalDecision.action, 'HOLD');
assert.equal(viewModel.finalDecision.executionIntent, 'WAIT_FOR_TRIGGER');

assert.equal(viewModel.changePanel.items.length >= 2, true);
assert.deepEqual(
  viewModel.changePanel.items.map((item) => item.field),
  ['Action', 'Execution intent'],
);

const noisyHoldReports = {
  investment_debate_state: {
    history: 'Bull Analyst: Hold is acceptable until confirmation.\nBear Analyst: Hold avoids chasing.',
    judge_decision: 'Research Manager: HOLD now while watching the trigger.',
  },
  trader_investment_plan: [
    'FINAL TRANSACTION PROPOSAL',
    'WAIT_FOR_TRIGGER and ACTION = HOLD now.',
    'POSITION_SIZE_PCT: N/A',
    'STOP_LOSS: 196.03',
  ].join('\n'),
  risk_debate_state: {
    history: 'Safe Analyst: Keep the hold until the trigger is confirmed.',
    safe_history: 'Safe Analyst: Keep the hold until the trigger is confirmed.',
    judge_decision: 'Risk Manager: HOLD remains appropriate; wait for trigger confirmation.',
  },
  final_trade_decision: [
    'BEGIN_DECISION_JSON {"action":"HOLD","execution_intent":"wait_for_trigger","position_size_pct":null,"rationale":"Hold remains appropriate until the trigger confirms."} END_DECISION_JSON',
  ].join('\n'),
};

const noisyHoldModel = buildDebateWorkflowViewModel(noisyHoldReports);

assert.equal(noisyHoldModel.traderProposal.action, 'HOLD');
assert.equal(noisyHoldModel.traderProposal.executionIntent, 'WAIT_FOR_TRIGGER');
assert.equal(noisyHoldModel.changePanel.items.length, 0);
assert.equal(noisyHoldModel.changePanel.unchanged, true);
