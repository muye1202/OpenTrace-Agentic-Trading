const SPEAKER_PATTERN = /^(Bull Analyst|Bear Analyst|Risky Analyst|Safe Analyst|Neutral Analyst|Research Manager|Risk Manager|Judge):\s*/i;

const ROLE_META = {
  'Bull Analyst': { stance: 'Bull thesis', tone: 'bull' },
  'Bear Analyst': { stance: 'Bear thesis', tone: 'bear' },
  'Risky Analyst': { stance: 'Aggressive execution', tone: 'risky' },
  'Safe Analyst': { stance: 'Capital preservation', tone: 'safe' },
  'Neutral Analyst': { stance: 'Balanced risk-reward', tone: 'neutral' },
  'Research Manager': { stance: 'Research judge', tone: 'judge' },
  'Risk Manager': { stance: 'Risk judge', tone: 'judge' },
};

const asObject = (value) => (value && typeof value === 'object' ? value : {});

const compactText = (value) => String(value || '').replace(/\s+/g, ' ').trim();

const firstSentence = (value, limit = 180) => {
  const text = compactText(value);
  if (!text) return '';
  const sentenceEnd = text.search(/[.!?](\s|$)/);
  const candidate = sentenceEnd > 40 ? text.slice(0, sentenceEnd + 1) : text;
  return candidate.length > limit ? `${candidate.slice(0, limit).trim()}...` : candidate;
};

const stripSpeaker = (text, fallbackSpeaker = '') => {
  const value = compactText(text);
  const match = value.match(SPEAKER_PATTERN);
  if (!match) return { speaker: fallbackSpeaker, content: value };
  return {
    speaker: normalizeSpeaker(match[1]),
    content: value.slice(match[0].length).trim(),
  };
};

const normalizeSpeaker = (speaker) => {
  const value = compactText(speaker).toLowerCase();
  if (value === 'judge') return 'Risk Manager';
  return Object.keys(ROLE_META).find((role) => role.toLowerCase() === value) || speaker;
};

export const splitDebateHistory = (history) => {
  const text = String(history || '').trim();
  if (!text) return [];

  const turns = [];
  let current = null;

  text.split(/\r?\n/).forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    const match = trimmed.match(SPEAKER_PATTERN);
    if (match) {
      if (current) turns.push(current);
      current = {
        speaker: normalizeSpeaker(match[1]),
        content: trimmed.slice(match[0].length).trim(),
      };
      return;
    }
    if (current) {
      current.content = `${current.content}\n${trimmed}`.trim();
    } else {
      current = { speaker: 'Agent', content: trimmed };
    }
  });

  if (current) turns.push(current);
  return turns.filter((turn) => turn.content);
};

const getLatestFromHistory = (history, speaker) => {
  const turns = splitDebateHistory(history).filter((turn) => turn.speaker === speaker);
  return turns.at(-1)?.content || '';
};

const participant = (role, history, currentValue = '') => {
  const meta = ROLE_META[role] || { stance: 'Debater', tone: 'neutral' };
  const latest = stripSpeaker(currentValue || getLatestFromHistory(history, role), role);
  const turns = splitDebateHistory(history).filter((turn) => turn.speaker === role);
  return {
    role,
    stance: meta.stance,
    tone: meta.tone,
    turnCount: turns.length,
    claim: firstSentence(latest.content || turns.at(-1)?.content),
    content: latest.content || turns.at(-1)?.content || '',
  };
};

const extractDecisionJson = (value) => {
  if (value && typeof value === 'object') return value;
  const text = String(value || '');
  const markerMatch = text.match(/BEGIN_DECISION_JSON\s*({[\s\S]*?})\s*END_DECISION_JSON/i);
  if (!markerMatch) return null;
  try {
    return JSON.parse(markerMatch[1]);
  } catch {
    return null;
  }
};

const extractPlanField = (text, names) => {
  const source = String(text || '');
  for (const name of names) {
    const pattern = new RegExp(`${name.replace(/_/g, '[_\\\\s-]*')}\\s*[:=]\\s*([^\\n\\r]+)`, 'i');
    const match = source.match(pattern);
    if (match) return match[1].replace(/[`"*]/g, '').trim();
  }
  return '';
};

const normalizeToken = (value) => String(value ?? '').trim().replace(/[.。]+$/g, '').trim();

const normalizeAction = (value) => {
  const text = normalizeToken(value).toUpperCase();
  const match = text.match(/\b(BUY|SELL|HOLD)\b/);
  return match ? match[1] : '';
};

const normalizeExecutionIntent = (value) => {
  const text = normalizeToken(value).toUpperCase().replace(/[\s-]+/g, '_');
  if (text.includes('WAIT_FOR_TRIGGER')) return 'WAIT_FOR_TRIGGER';
  if (text.includes('ACT_NOW')) return 'ACT_NOW';
  return '';
};

const normalizeNullable = (value) => {
  const text = normalizeToken(value);
  if (!text) return '';
  if (/^(N\/A|NA|NONE|NULL|UNSPECIFIED|UNDEFINED)$/i.test(text)) return '';
  return text;
};

const normalizeComparable = (value) => String(value ?? '').trim().toUpperCase();

const buildTraderProposal = (text) => {
  const rawAction = extractPlanField(text, ['ACTION', 'FINAL_ACTION']);
  const rawExecutionIntent = extractPlanField(text, ['EXECUTION_INTENT', 'INTENT']) || String(text || '');
  return {
    action: normalizeAction(rawAction) || 'Unspecified',
    executionIntent: normalizeExecutionIntent(rawExecutionIntent) || 'Unspecified',
    positionSize: normalizeNullable(extractPlanField(text, ['POSITION_SIZE_PCT', 'POSITION_SIZE', 'SIZE'])) || 'Unspecified',
    stopLoss: normalizeNullable(extractPlanField(text, ['STOP_LOSS', 'STOP'])) || 'Unspecified',
    raw: String(text || ''),
  };
};

const buildFinalDecision = (text, structuredDecision) => {
  const parsed = extractDecisionJson(structuredDecision) || extractDecisionJson(text) || {};
  const action = normalizeAction(parsed.action || extractPlanField(text, ['ACTION']));
  const executionIntent = normalizeExecutionIntent(parsed.execution_intent || parsed.executionIntent || extractPlanField(text, ['EXECUTION_INTENT']));
  return {
    action: action || 'Unspecified',
    executionIntent: executionIntent || 'Unspecified',
    positionSize: normalizeNullable(parsed.position_size_pct ?? parsed.positionSize) || 'Unspecified',
    stopLoss: normalizeNullable(parsed.stop_loss ?? parsed.stopLoss) || 'Unspecified',
    takeProfit: normalizeNullable(parsed.take_profit ?? parsed.takeProfit) || 'Unspecified',
    rationale: parsed.rationale || firstSentence(text, 260),
    raw: String(text || ''),
  };
};

const changeItem = (field, before, after, impact) => ({
  field,
  before: before === null || before === undefined || before === '' ? 'Unspecified' : String(before),
  after: after === null || after === undefined || after === '' ? 'Unspecified' : String(after),
  impact,
});

const buildChangePanel = (traderProposal, finalDecision) => {
  const candidates = [
    changeItem('Action', traderProposal.action, finalDecision.action, 'Final trade direction changed after risk review.'),
    changeItem('Execution intent', traderProposal.executionIntent, finalDecision.executionIntent, 'Risk debate changed when or how the trade should execute.'),
    changeItem('Position size', traderProposal.positionSize, finalDecision.positionSize, 'Risk review adjusted capital exposure.'),
    changeItem('Stop loss', traderProposal.stopLoss, finalDecision.stopLoss, 'Risk review adjusted downside control.'),
  ];
  const items = candidates.filter((item) => (
    normalizeNullable(item.before)
    && normalizeNullable(item.after)
    && normalizeComparable(item.before) !== normalizeComparable(item.after)
  ));
  return {
    items,
    unchanged: items.length === 0,
  };
};

const buildWorkflowSteps = (reports, summary) => [
  { id: 'analysts', label: 'Analyst reports', status: reports.market_report || reports.news_report || reports.fundamentals_report ? 'available' : 'missing', takeaway: 'Evidence inputs assembled.' },
  { id: 'research_debate', label: 'Bull/Bear debate', status: summary.researchTurns > 0 ? 'available' : 'missing', takeaway: `${summary.researchTurns} research turn${summary.researchTurns === 1 ? '' : 's'}.` },
  { id: 'research_manager', label: 'Research manager', status: reports.investment_debate_state?.judge_decision ? 'available' : 'missing', takeaway: firstSentence(reports.investment_debate_state?.judge_decision) || 'No judge decision captured.' },
  { id: 'trader', label: 'Trader proposal', status: reports.trader_investment_plan ? 'available' : 'missing', takeaway: 'Research translated into an executable proposal.' },
  { id: 'risk_debate', label: 'Risk debate', status: summary.riskTurns > 0 ? 'available' : 'missing', takeaway: `${summary.riskTurns} risk turn${summary.riskTurns === 1 ? '' : 's'}.` },
  { id: 'risk_manager', label: 'Risk manager', status: reports.risk_debate_state?.judge_decision ? 'available' : 'missing', takeaway: firstSentence(reports.risk_debate_state?.judge_decision) || 'No risk judge decision captured.' },
  { id: 'final', label: 'Final decision', status: reports.final_trade_decision ? 'available' : 'missing', takeaway: 'Canonical trade parameters finalized.' },
];

export const buildDebateWorkflowViewModel = (reportsValue = {}) => {
  const reports = asObject(reportsValue);
  const investmentDebate = asObject(reports.investment_debate_state);
  const riskDebate = asObject(reports.risk_debate_state);
  const researchTurns = splitDebateHistory(investmentDebate.history);
  const riskTurns = splitDebateHistory(riskDebate.history);
  const traderProposal = buildTraderProposal(reports.trader_investment_plan);
  const finalDecision = buildFinalDecision(reports.final_trade_decision, reports.final_trade_decision_structured);
  const summary = {
    researchTurns: researchTurns.length || Number(investmentDebate.count || 0),
    riskTurns: riskTurns.length || Number(riskDebate.count || 0),
    totalTurns: (researchTurns.length || Number(investmentDebate.count || 0)) + (riskTurns.length || Number(riskDebate.count || 0)),
  };

  return {
    hasDebate: Boolean(investmentDebate.history || riskDebate.history || investmentDebate.judge_decision || riskDebate.judge_decision),
    workflowSteps: buildWorkflowSteps(reports, summary),
    summary,
    researchArena: {
      title: 'Research debate',
      participants: [
        participant('Bull Analyst', investmentDebate.bull_history || investmentDebate.history),
        participant('Bear Analyst', investmentDebate.bear_history || investmentDebate.history),
      ],
      turns: researchTurns,
      judge: {
        role: 'Research Manager',
        stance: ROLE_META['Research Manager'].stance,
        tone: ROLE_META['Research Manager'].tone,
        content: investmentDebate.judge_decision || investmentDebate.current_response || '',
        claim: firstSentence(investmentDebate.judge_decision || investmentDebate.current_response),
      },
    },
    traderProposal,
    riskArena: {
      title: 'Risk debate',
      participants: [
        participant('Risky Analyst', riskDebate.risky_history || riskDebate.history, riskDebate.current_risky_response),
        participant('Safe Analyst', riskDebate.safe_history || riskDebate.history, riskDebate.current_safe_response),
        participant('Neutral Analyst', riskDebate.neutral_history || riskDebate.history, riskDebate.current_neutral_response),
      ],
      turns: riskTurns,
      judge: {
        role: 'Risk Manager',
        stance: ROLE_META['Risk Manager'].stance,
        tone: ROLE_META['Risk Manager'].tone,
        content: riskDebate.judge_decision || '',
        claim: firstSentence(riskDebate.judge_decision),
      },
    },
    finalDecision,
    changePanel: buildChangePanel(traderProposal, finalDecision),
  };
};
