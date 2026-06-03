import { memo, useMemo } from 'react';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import { buildDebateWorkflowViewModel } from './debateWorkflowViewModel';

const ToneBadge = ({ children, tone = 'neutral' }) => (
  <span className={`dwp-badge dwp-badge--${tone}`}>{children}</span>
);

const WorkflowStep = ({ step, index }) => (
  <li className={`dwp-step dwp-step--${step.status}`}>
    <span className="dwp-step__index">{index + 1}</span>
    <div>
      <strong>{step.label}</strong>
      <p>{step.takeaway}</p>
    </div>
  </li>
);

const Metric = ({ label, value }) => (
  <div className="dwp-metric">
    <strong>{value}</strong>
    <span>{label}</span>
  </div>
);

const RawMarkdown = ({ children }) => {
  const text = String(children || '').trim();
  if (!text) return <p className="dwp-muted">No raw text captured.</p>;
  return (
    <div className="dwp-raw markdown-content">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{text}</ReactMarkdown>
    </div>
  );
};

const ParticipantCard = ({ participant }) => (
  <article className={`dwp-argument dwp-argument--${participant.tone}`}>
    <div className="dwp-argument__header">
      <div>
        <strong>{participant.role}</strong>
        <span>{participant.stance}</span>
      </div>
      <ToneBadge tone={participant.tone}>{participant.turnCount} turn{participant.turnCount === 1 ? '' : 's'}</ToneBadge>
    </div>
    <p>{participant.claim || 'No summarized claim captured.'}</p>
    <details className="dwp-details">
      <summary>Raw argument</summary>
      <RawMarkdown>{participant.content}</RawMarkdown>
    </details>
  </article>
);

const JudgeCard = ({ judge }) => (
  <article className="dwp-judge">
    <div className="dwp-argument__header">
      <div>
        <strong>{judge.role}</strong>
        <span>{judge.stance}</span>
      </div>
      <ToneBadge tone="judge">Resolution</ToneBadge>
    </div>
    <p>{judge.claim || 'No judge resolution captured.'}</p>
    <details className="dwp-details">
      <summary>Judge text</summary>
      <RawMarkdown>{judge.content}</RawMarkdown>
    </details>
  </article>
);

const Arena = ({ arena }) => (
  <section className="dwp-section">
    <div className="dwp-section__header">
      <div>
        <h4>{arena.title}</h4>
        <p>{arena.turns.length} captured turn{arena.turns.length === 1 ? '' : 's'} before judge resolution.</p>
      </div>
    </div>
    <div className="dwp-arguments">
      {arena.participants.map((participant) => (
        <ParticipantCard key={participant.role} participant={participant} />
      ))}
    </div>
    <JudgeCard judge={arena.judge} />
    <details className="dwp-details dwp-details--timeline">
      <summary>Turn-by-turn transcript</summary>
      <div className="dwp-turns">
        {arena.turns.length > 0 ? arena.turns.map((turn, index) => (
          <div key={`${turn.speaker}-${index}`} className="dwp-turn">
            <ToneBadge>{turn.speaker}</ToneBadge>
            <p>{turn.content}</p>
          </div>
        )) : (
          <p className="dwp-muted">No turn-level transcript captured.</p>
        )}
      </div>
    </details>
  </section>
);

const ChangePanel = ({ changePanel, traderProposal, finalDecision }) => (
  <section className="dwp-section dwp-section--changes">
    <div className="dwp-section__header">
      <div>
        <h4>What changed after debate</h4>
        <p>Highlights material differences between the Trader proposal and Risk Manager final decision.</p>
      </div>
    </div>
    <div className="dwp-change-grid">
      {changePanel.unchanged ? (
        <div className="dwp-change-empty">
          <strong>No material parameter changes detected.</strong>
          <p>The final decision preserved the comparable action and execution parameters. Review the Risk Manager resolution below for qualitative rationale.</p>
        </div>
      ) : changePanel.items.map((item) => (
        <div key={item.field} className="dwp-change">
          <span>{item.field}</span>
          <div className="dwp-change__values">
            <code>{item.before}</code>
            <span aria-hidden="true">to</span>
            <code>{item.after}</code>
          </div>
          <p>{item.impact}</p>
        </div>
      ))}
    </div>
    <div className="dwp-proposal-strip">
      <div>
        <span>Trader proposal</span>
        <strong>{traderProposal.action}</strong>
        <small>{traderProposal.executionIntent}</small>
      </div>
      <div>
        <span>Final decision</span>
        <strong>{finalDecision.action}</strong>
        <small>{finalDecision.executionIntent}</small>
      </div>
    </div>
  </section>
);

const DebateWorkflowPanel = ({ reports }) => {
  const viewModel = useMemo(() => buildDebateWorkflowViewModel(reports), [reports]);

  if (!viewModel.hasDebate) {
    return (
      <div className="dwp-panel">
        <div className="dwp-empty">
          <p>No debate workflow data is available for this report.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="dwp-panel">
      <div className="dwp-hero">
        <div>
          <h3>Debate workflow</h3>
          <p>Post-run audit of how adversarial agents shaped the final trade decision.</p>
        </div>
        <div className="dwp-metrics">
          <Metric label="Research turns" value={viewModel.summary.researchTurns} />
          <Metric label="Risk turns" value={viewModel.summary.riskTurns} />
          <Metric label="Total turns" value={viewModel.summary.totalTurns} />
        </div>
      </div>

      <ol className="dwp-workflow">
        {viewModel.workflowSteps.map((step, index) => (
          <WorkflowStep key={step.id} step={step} index={index} />
        ))}
      </ol>

      <ChangePanel
        changePanel={viewModel.changePanel}
        traderProposal={viewModel.traderProposal}
        finalDecision={viewModel.finalDecision}
      />

      <Arena arena={viewModel.researchArena} />
      <Arena arena={viewModel.riskArena} />
    </div>
  );
};

export default memo(DebateWorkflowPanel);
