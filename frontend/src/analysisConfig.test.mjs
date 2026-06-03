import assert from 'node:assert/strict';

import {
  DEFAULT_ANALYSTS,
  REPORT_SECTIONS,
  REPORT_GROUPS,
  ANALYST_SUMMARY_LABEL,
  DEFAULT_EXPANDED_REPORT_SECTIONS,
  isReportSectionExpanded,
  buildContinueAnalysisOverrides,
} from './analysisConfig.js';

assert.deepEqual(DEFAULT_ANALYSTS, [
  'catalyst',
  'market',
  'social',
  'news',
  'fundamentals',
]);

assert.deepEqual(REPORT_SECTIONS.slice(0, 6), [
  ['discovery_report', 'Candidate Stocks'],
  ['catalyst_report', 'Catalyst'],
  ['market_report', 'Market'],
  ['sentiment_report', 'Sentiment'],
  ['news_report', 'News'],
  ['fundamentals_report', 'Fundamentals'],
]);

assert.deepEqual(
  REPORT_SECTIONS.filter(([sectionKey]) => DEFAULT_ANALYSTS
    .map((analyst) => analyst === 'social' ? 'sentiment_report' : `${analyst}_report`)
    .includes(sectionKey)),
  [
    ['catalyst_report', 'Catalyst'],
    ['market_report', 'Market'],
    ['sentiment_report', 'Sentiment'],
    ['news_report', 'News'],
    ['fundamentals_report', 'Fundamentals'],
  ],
);

assert.equal(ANALYST_SUMMARY_LABEL, 'Catalyst, Market, Social, News, Fundamentals');
assert.equal(REPORT_SECTIONS.some(([key, label]) => key === 'debate_workflow' && label === 'Debate Workflow'), true);
assert.deepEqual(
  REPORT_GROUPS.find((group) => group.id === 'evidence')?.sections,
  ['evidence_graph', 'decision_trace', 'debate_workflow'],
);
assert.deepEqual(
  REPORT_GROUPS.find((group) => group.id === 'pipeline')?.sections,
  ['trader_investment_plan'],
);

assert.deepEqual(DEFAULT_EXPANDED_REPORT_SECTIONS, {});

assert.equal(isReportSectionExpanded('catalyst_report', DEFAULT_EXPANDED_REPORT_SECTIONS), false);
assert.equal(isReportSectionExpanded('decision_trace', DEFAULT_EXPANDED_REPORT_SECTIONS), false);
assert.equal(isReportSectionExpanded('final_trade_decision', DEFAULT_EXPANDED_REPORT_SECTIONS), false);
assert.equal(isReportSectionExpanded('decision_trace', { decision_trace: true }), true);
assert.equal(isReportSectionExpanded('final_trade_decision', { final_trade_decision: false }), false);

assert.deepEqual(
  buildContinueAnalysisOverrides({
    id: 19,
    ticker: 'MRVL',
    analysis_date: '2026-05-26',
    time_horizon: '2-3 months',
  }),
  {
    ticker: 'MRVL',
    analysisDate: '2026-05-26',
    timeHorizon: '2-3 months',
    continuePrevious: true,
    continueSessionId: 19,
  },
);
