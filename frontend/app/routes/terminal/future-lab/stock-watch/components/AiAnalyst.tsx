import { useState } from 'react';
import { useAgentAvailabilityQuery, useAskAgentMutation } from '$contexts/signals/queries';
import { cx } from '$shared/ui/cx';
import s from '../stock-watch.module.css';

/**
 * Everything the page has actually loaded, assembled for the model to read.
 *
 * Built from the same values on screen and nothing else. The model is told
 * explicitly which figures are missing, which are simulated and which are
 * model-derived, because an analyst that does not know its inputs are
 * synthetic will write confident prose about a market that did not happen.
 */
export interface EvidencePack {
  symbol: string;
  asOf: string;
  dataSource: string;
  feedWarning: string;
  marketOpen: boolean;
  spot?: number | undefined;
  changePercent?: number | undefined;
  structure: string;
  structureRule: string;
  atr?: number | undefined;
  relativeVolume?: number | undefined;
  gap?: string | undefined;
  levels: { label: string; price: number; timeframe: string }[];
  futuresPrice?: number | undefined;
  futuresBasisPercent?: number | undefined;
  futuresState: string;
  futuresOi?: number | undefined;
  futuresOiChangePercent?: number | undefined;
  rolloverPercent?: number | undefined;
  expiry?: string | undefined;
  daysToExpiry: number;
  atmIv?: number | undefined;
  historicalVol?: number | undefined;
  pcrOi?: number | undefined;
  pcrVolume?: number | undefined;
  maxPain?: number | undefined;
  topCallOi: { strike: number; oi: number }[];
  topPutOi: { strike: number; oi: number }[];
  buildups: { strike: number; type: string; state: string }[];
  liquidityWarnings: string[];
  missing: string[];
}

/** The instruction the model is given, verbatim. Shown to the reader on request. */
export function buildPrompt(pack: EvidencePack): string {
  const lines = (label: string, rows: string[]) =>
    rows.length ? `${label}:\n${rows.map((row) => `  - ${row}`).join('\n')}` : `${label}: none`;

  return [
    `You are reviewing ${pack.symbol} for an Indian single-stock F&O trader.`,
    '',
    'Use ONLY the data below. Do not introduce prices, dates, news, corporate events or',
    'statistics that are not in it. Where something is listed as missing or simulated, say so',
    'rather than working around it. Do not give a probability unless the data supports one, and',
    'do not state or imply any outcome is guaranteed. You are not placing orders.',
    '',
    'Structure your answer under these headings, and keep observations separate from',
    'interpretations and interpretations separate from hypothetical trade scenarios:',
    '1. Underlying market structure  2. Bullish evidence  3. Bearish evidence',
    '4. Futures positioning  5. Options positioning  6. Key technical levels',
    '7. Volatility and greeks risk  8. Liquidity and execution risk',
    '9. Upcoming events  10. Possible trade scenarios  11. Entry conditions',
    '12. Stop-loss and invalidation  13. Risk/reward considerations  14. Missing or stale data',
    '',
    'Cite the specific figure from the data for every claim you make.',
    '',
    '--- DATA ---',
    `As of: ${pack.asOf} (source: ${pack.dataSource}${pack.feedWarning ? `; WARNING: ${pack.feedWarning}` : ''})`,
    `Market open: ${pack.marketOpen}`,
    `Spot: ${pack.spot ?? 'unknown'} (${pack.changePercent ?? 'unknown'}% on the day)`,
    `Structure: ${pack.structure} — ${pack.structureRule}`,
    `ATR(14): ${pack.atr ?? 'unknown'}; relative volume: ${pack.relativeVolume ?? 'unknown'}`,
    `Gap: ${pack.gap ?? 'none'}`,
    lines(
      'Levels',
      pack.levels.map((level) => `${level.label} ${level.price} (${level.timeframe})`)
    ),
    `Futures: ${pack.futuresPrice ?? 'unknown'}, basis ${pack.futuresBasisPercent ?? 'unknown'}%, classified ${pack.futuresState}`,
    `Futures OI: ${pack.futuresOi ?? 'unknown'} (${pack.futuresOiChangePercent ?? 'unknown'}%); rollover ${pack.rolloverPercent ?? 'unknown'}%`,
    `Options expiry: ${pack.expiry ?? 'unknown'}, ${pack.daysToExpiry} days away`,
    `ATM IV: ${pack.atmIv ?? 'unknown'}%; realised vol: ${pack.historicalVol ?? 'unknown'}%`,
    `PCR by OI: ${pack.pcrOi ?? 'unknown'}; by volume: ${pack.pcrVolume ?? 'unknown'}; max pain: ${pack.maxPain ?? 'unknown'}`,
    lines(
      'Highest call OI',
      pack.topCallOi.map((row) => `${row.strike}: ${row.oi}`)
    ),
    lines(
      'Highest put OI',
      pack.topPutOi.map((row) => `${row.strike}: ${row.oi}`)
    ),
    lines(
      'Option build-ups detected',
      pack.buildups.map((row) => `${row.strike} ${row.type}: ${row.state}`)
    ),
    lines('Liquidity warnings', pack.liquidityWarnings),
    lines('Known missing or unavailable data', pack.missing),
    '--- END DATA ---'
  ].join('\n');
}

interface Props {
  symbol: string;
  pack: EvidencePack;
}

/**
 * A structured read of the data on this page, written by the terminal's own
 * analyst model.
 *
 * Grounded rather than free-running: the prompt carries the page's loaded
 * figures and forbids anything outside them, including invented news and
 * invented probabilities. It cannot place an order, and the panel says so.
 *
 * When no model is configured the panel reports that plainly instead of
 * degrading to a canned "analysis" — a rule-based paragraph dressed as an AI
 * read would be the same dishonesty in a cheaper form.
 */
export default function AiAnalyst({ symbol, pack }: Props) {
  const availability = useAgentAvailabilityQuery();
  const ask = useAskAgentMutation(symbol);
  const [showPrompt, setShowPrompt] = useState(false);

  const available = availability.data?.available ?? false;
  const answer = ask.data?.answer;

  return (
    <section className={s.panel}>
      <div className={s.panelHead}>
        <div>
          <h2 className={s.panelTitle}>AI trade analyst</h2>
          <p className={s.panelSub}>
            Reads only what this page has loaded — no outside facts, no order placement
          </p>
        </div>
        <div className={s.panelActions}>
          <button
            type="button"
            className={cx(s.action, showPrompt && s.actionPrimary)}
            onClick={() => setShowPrompt((on) => !on)}
          >
            Show the data it is given
          </button>
          <button
            type="button"
            className={cx(s.action, s.actionPrimary)}
            disabled={!available || ask.isPending}
            onClick={() => ask.mutate(buildPrompt(pack))}
          >
            {ask.isPending ? 'Analysing…' : 'Run analysis'}
          </button>
        </div>
      </div>

      <div className={s.panelBody}>
        {availability.isPending ? (
          <p className={s.empty}>Checking whether a model is configured…</p>
        ) : !available ? (
          <p className={cx(s.notice, s.noticeWarn)}>
            <span>
              No language model is configured for this workspace, so no analysis can be produced.
              This panel will not substitute a rule-based paragraph for one — a canned read
              presented as an AI analysis is the same false confidence in a cheaper form. Configure
              a model under Settings → AI to enable it.
            </span>
          </p>
        ) : null}

        {showPrompt ? (
          <pre
            className={cx(s.notice, s.muted)}
            style={{
              marginTop: 'var(--cn-space-3)',
              whiteSpace: 'pre-wrap',
              fontFamily: 'var(--cn-font-mono)',
              fontSize: '0.6875rem',
              maxHeight: '24rem',
              overflow: 'auto'
            }}
          >
            {buildPrompt(pack)}
          </pre>
        ) : null}

        {ask.isError ? (
          <p className={cx(s.notice, s.noticeDanger)} style={{ marginTop: 'var(--cn-space-3)' }}>
            <span>The analysis request failed. Nothing is shown rather than a partial read.</span>
          </p>
        ) : null}

        {answer ? (
          <div
            className={s.panelSub}
            style={{
              marginTop: 'var(--cn-space-3)',
              whiteSpace: 'pre-wrap',
              fontSize: 'var(--cn-text-sm)',
              lineHeight: 1.65,
              color: 'var(--cn-text)'
            }}
          >
            {answer}
          </div>
        ) : null}

        {pack.missing.length > 0 ? (
          <p className={cx(s.notice, s.noticeWarn)} style={{ marginTop: 'var(--cn-space-3)' }}>
            <span>
              <strong>Known gaps in the evidence</strong>, passed to the model explicitly so it
              cannot write around them: {pack.missing.join('; ')}.
            </span>
          </p>
        ) : null}

        <p className={s.notice} style={{ marginTop: 'var(--cn-space-2)' }}>
          <span>
            The analyst reads market data and writes a structured review. It does not have access to
            your positions, it cannot place or modify orders, and its interpretations are
            interpretations — the figures it cites are the part you can verify, and you should.
          </span>
        </p>
      </div>
    </section>
  );
}
