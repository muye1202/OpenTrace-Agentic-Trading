export const DEFAULT_ANALYSTS = [
  'catalyst',
  'market',
  'social',
  'news',
  'fundamentals',
];

export const REPORT_SECTIONS = [
  ['discovery_report', 'Candidate Stocks'],
  ['catalyst_report', 'Catalyst'],
  ['market_report', 'Market'],
  ['sentiment_report', 'Sentiment'],
  ['news_report', 'News'],
  ['fundamentals_report', 'Fundamentals'],
  ['evidence_graph', 'Evidence Graph'],
  ['decision_trace', 'Decision Trace'],
  ['debate_workflow', 'Debate Workflow'],
  ['trader_investment_plan', 'Trader Plan'],
  ['final_trade_decision', 'Final Decision'],
];

export const ANALYST_SUMMARY_LABEL = 'Catalyst, Market, Social, News, Fundamentals';

export const DEFAULT_EXPANDED_REPORT_SECTIONS = {};

export const isReportSectionExpanded = (sectionKey, expandedSections = DEFAULT_EXPANDED_REPORT_SECTIONS) => (
  expandedSections[sectionKey] === true
);

export const REPORT_GROUPS = [
  {
    id: 'analyst_reports',
    label: 'Analyst Reports',
    icon: '📈',
    sections: ['catalyst_report', 'market_report', 'sentiment_report', 'news_report', 'fundamentals_report'],
  },
  {
    id: 'evidence',
    label: 'Evidence & Tracing',
    icon: '🔍',
    sections: ['evidence_graph', 'decision_trace', 'debate_workflow'],
  },
  {
    id: 'pipeline',
    label: 'Trading Pipeline',
    icon: '⚙️',
    sections: ['trader_investment_plan'],
  },
  {
    id: 'final',
    label: 'Final Verdict',
    icon: '🎯',
    sections: ['final_trade_decision'],
  }
];

export const buildContinueAnalysisOverrides = (session) => ({
  ticker: session?.ticker || '',
  analysisDate: session?.analysis_date || '',
  timeHorizon: session?.time_horizon || '',
  continuePrevious: true,
  continueSessionId: session?.id ?? null,
});
