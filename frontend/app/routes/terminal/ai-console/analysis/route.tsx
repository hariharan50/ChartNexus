import { useEffect, useRef, useState, type KeyboardEvent } from 'react';
import { Link } from 'react-router';
import { useGuidanceHistoryQuery, useGuidanceQuery } from '$contexts/signals/queries';
import type {
  Decision,
  Guidance,
  Horizon,
  HorizonCall,
  Levels,
  Scaffold
} from '$contexts/signals/types';
import { cx } from '$shared/ui/cx';
import DataSourceBadge from '$shared/ui/DataSourceBadge';
import {
  HORIZONS,
  INSTRUMENTS,
  bandExplainer,
  biasPhrase,
  decisionClass,
  driverHint,
  driverLabel,
  fmtAgo,
  fmtPrice,
  fmtRatio,
  holdBand,
  horizonConsensus,
  isTodayIST,
  levelLadder,
  marketStatusIST,
  nowLabelIST,
  pcrSentiment,
  regimeLabel,
  scaffoldPoints,
  spotPositionPct,
  timeIST,
  vixAbsoluteChange,
  vixEnvironment
} from '../ai-console-data';
import ConsoleHeader from '../components/ConsoleHeader';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [
  { title: 'Market Analysis · AI Console · ChartNexus' }
];

/** The agent's name, shown throughout the console. */
const AGENT_NAME = 'Hella';

const DISCLAIMER =
  'Algorithmic signal derived from market data — not investment advice, and not a ' +
  'personalised recommendation to buy or sell any instrument. Levels and contracts are ' +
  'illustrative only.';

const HORIZON_SHORT: Record<Horizon, string> = {
  intraday: 'intraday',
  end_of_day: 'end of day',
  swing: 'swing'
};

export default function NiftyAnalysis() {
  const [instIdx, setInstIdx] = useState(0);
  const [horizon, setHorizon] = useState<Horizon>('intraday');
  const instrument = INSTRUMENTS[instIdx] ?? INSTRUMENTS[0];

  const query = useGuidanceQuery(instrument.symbol);
  const guidance = query.data;
  const now = useNow(1000);

  return (
    <div className={s.page}>
      <ConsoleHeader
        title="Market Analysis"
        subtitle={
          <>
            Calibrated calls across three horizons, the drivers behind each, the levels that matter
            and the risk — read by <strong>{AGENT_NAME}</strong>.
          </>
        }
        instIdx={instIdx}
        onSelect={setInstIdx}
        views={
          <div className={s.freshness}>
            <span className={s.freshText} aria-live="polite">
              {query.isFetching
                ? 'Updating…'
                : query.dataUpdatedAt
                  ? `Updated ${fmtAgo(query.dataUpdatedAt, now)}`
                  : ''}
            </span>
            <button
              type="button"
              className={s.refresh}
              onClick={() => void query.refetch()}
              disabled={query.isFetching}
              aria-label="Refresh analysis"
              title="Refresh now"
            >
              ↻
            </button>
          </div>
        }
      />

      {query.isLoading && !guidance ? (
        <Skeleton />
      ) : query.isError || !guidance ? (
        <div className={s.panel}>
          <div className={s.state}>
            Guidance is unavailable for {instrument.symbol} right now.{' '}
            <button type="button" className={s.linkButton} onClick={() => void query.refetch()}>
              Try again
            </button>
          </div>
        </div>
      ) : (
        <>
          <ContextCards guidance={guidance} />
          <div className={s.layout}>
            <div className={s.column}>
              <CallPanel guidance={guidance} horizon={horizon} onHorizon={setHorizon} />
            </div>
            <div className={s.column}>
              <LevelsPanel levels={guidance.levels} />
              <ScaffoldPanel
                scaffold={guidance.scaffold}
                actionable={guidance.is_actionable}
                decision={guidance.decision}
              />
              <HistoryPanel symbol={guidance.symbol} />
            </div>
          </div>
          <StatusBar provenance={guidance.provenance} />
        </>
      )}
    </div>
  );
}

/** A clock that re-renders the "updated N s ago" line. */
function useNow(intervalMs: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);
  return now;
}

function Skeleton() {
  return (
    <div className={s.skeleton} aria-busy="true" aria-label={`${AGENT_NAME} is reading the tape`}>
      <div className={s.cards}>
        {[0, 1, 2, 3].map((index) => (
          <div key={index} className={cx(s.card, s.skeletonBlock)} />
        ))}
      </div>
      <div className={s.layout}>
        <div className={cx(s.panel, s.skeletonBlock, s.skeletonTall)} />
        <div className={cx(s.panel, s.skeletonBlock, s.skeletonTall)} />
      </div>
    </div>
  );
}

/* -- Context cards --------------------------------------------------------- */

function ContextCards({ guidance }: { guidance: Guidance }) {
  const consensus = horizonConsensus(guidance.horizons);

  const vix = guidance.context.india_vix;
  const vixPct = guidance.context.india_vix_change_percent;
  const vixAbs = vixAbsoluteChange(vix, vixPct);
  const env = vixEnvironment(vix);
  const pcr = guidance.context.pcr;
  const pcrRead = pcrSentiment(pcr);
  const vixArrow = vixPct == null || vixPct === 0 ? '' : vixPct < 0 ? '▼ ' : '▲ ';

  return (
    <div className={s.cards}>
      <div className={cx(s.card, s.tinted, s.cardBlue)}>
        <span className={s.cardTitle}>✦ Signal consensus</span>
        <span className={s.cardRegime}>{consensus.label}</span>
        <div className={s.voteRow} aria-label="Call per horizon">
          {HORIZONS.map((h) => {
            const call = guidance.horizons.find((c) => c.horizon === h.key);
            return (
              <span key={h.key} className={s.vote} title={`${h.label}: ${call?.decision ?? '—'}`}>
                <span className={s.voteLabel}>{h.label}</span>
                <span className={s.voteValue}>{call?.decision ?? '—'}</span>
              </span>
            );
          })}
        </div>
        <span className={s.cardNote}>Average confidence {consensus.averageConfidence}%</span>
      </div>

      <div className={cx(s.card, s.tinted, s.cardRed)}>
        <span className={s.cardTitle}>⧉ Market regime</span>
        <span className={s.cardRegime}>{regimeLabel(guidance.regime)}</span>
        <span className={s.cardSub}>{biasPhrase(guidance.decision)}</span>
        <span className={s.pill}>{env.label}</span>
      </div>

      <div className={cx(s.card, s.tinted, s.cardPink)}>
        <span className={s.cardTitle}>⟁ Volatility (India VIX)</span>
        <span className={s.cardBig}>{vix == null ? '—' : vix.toFixed(2)}</span>
        {vixAbs != null && vixPct != null ? (
          <span className={s.cardDelta}>
            {vixArrow}
            {vixAbs > 0 ? '+' : ''}
            {vixAbs.toFixed(2)} ({vixPct > 0 ? '+' : ''}
            {vixPct.toFixed(1)}%)
          </span>
        ) : (
          <span className={s.cardSub}>No change data</span>
        )}
        <span className={s.cardNote}>
          {env.note}. A rising VIX means wider swings and pricier options.
        </span>
      </div>

      <div className={cx(s.card, s.tinted, s.cardLavender)}>
        <span className={s.cardTitle}>◪ PCR (total)</span>
        <span className={s.cardBig}>{pcr == null ? '—' : pcr.toFixed(2)}</span>
        <span className={s.cardSub}>{pcrRead.label}</span>
        <span className={s.cardNote}>
          {pcrRead.note}. Above 1 means more puts written than calls.
        </span>
      </div>
    </div>
  );
}

/* -- The call -------------------------------------------------------------- */

/** The selected horizon's call, or the intraday headline as a fallback. */
function callFor(guidance: Guidance, horizon: Horizon): HorizonCall | undefined {
  return (
    guidance.horizons.find((c) => c.horizon === horizon) ??
    guidance.horizons.find((c) => c.horizon === 'intraday') ??
    guidance.horizons[0]
  );
}

function CallPanel({
  guidance,
  horizon,
  onHorizon
}: {
  guidance: Guidance;
  horizon: Horizon;
  onHorizon: (h: Horizon) => void;
}) {
  const call = callFor(guidance, horizon);
  const decision = call?.decision ?? guidance.decision;
  const confidence = call?.confidence ?? guidance.confidence;
  const dc = decisionClass(decision);
  const word =
    decision === 'BUY' ? 'leans bullish' : decision === 'SELL' ? 'leans bearish' : 'no clear edge';
  const coverage = guidance.coverage;

  return (
    <div className={cx(s.panel, s.hero, s[dc])}>
      <div className={s.heroTop}>
        <span className={cx(s.regime, s[dc])}>{regimeLabel(guidance.regime)}</span>
        <DataSourceBadge source={guidance.provenance} />
      </div>

      <HorizonStrip guidance={guidance} horizon={horizon} onHorizon={onHorizon} />

      <div className={s.heroMain}>
        <div className={s.heroLeft}>
          <span className={cx(s.chip, s[dc])}>{decision}</span>
          <div>
            <div className={s.symbol}>{guidance.symbol}</div>
            <div className={s.decisionWord}>
              {word} · {HORIZON_SHORT[call?.horizon ?? horizon]}
            </div>
          </div>
        </div>
        <div className={s.ringWrap}>
          <ConfidenceRing value={confidence} decision={decision} />
          {coverage != null ? (
            <span
              className={s.coverage}
              title="Share of the model's inputs that had data. Thin data caps confidence."
            >
              Data coverage {Math.round(coverage * 100)}%
            </span>
          ) : null}
        </div>
      </div>

      {call ? <ProbabilityGauge call={call} /> : null}
      {call ? <DriverBars call={call} /> : null}

      <p className={s.rationale}>{guidance.rationale}</p>

      {guidance.warnings.length ? (
        <div className={s.callout} role="note">
          <span className={s.calloutTitle}>⚠ Before acting on this</span>
          <ul>
            {guidance.warnings.map((warning) => (
              <li key={warning}>{warning}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <AskHella symbol={guidance.symbol} decision={decision} horizon={call?.horizon ?? horizon} />
    </div>
  );
}

function HorizonStrip({
  guidance,
  horizon,
  onHorizon
}: {
  guidance: Guidance;
  horizon: Horizon;
  onHorizon: (h: Horizon) => void;
}) {
  const refs = useRef<Array<HTMLButtonElement | null>>([]);

  const move = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = (index + step + HORIZONS.length) % HORIZONS.length;
    const target = HORIZONS[next];
    if (target) {
      onHorizon(target.key);
      refs.current[next]?.focus();
    }
  };

  return (
    <div className={s.switcher} role="tablist" aria-label="Signal horizon">
      {HORIZONS.map((h, index) => {
        const call = guidance.horizons.find((c) => c.horizon === h.key);
        const selected = h.key === horizon;
        const dc = call ? decisionClass(call.decision) : 'hold';
        return (
          <button
            key={h.key}
            ref={(node) => {
              refs.current[index] = node;
            }}
            type="button"
            role="tab"
            aria-selected={selected}
            tabIndex={selected ? 0 : -1}
            className={cx(s.switchBtn, selected && s.switchOn)}
            onClick={() => onHorizon(h.key)}
            onKeyDown={(event) => move(event, index)}
          >
            <span className={s.switchHead}>
              <span className={s.switchLabel}>{h.label}</span>
              {call ? <span className={cx(s.miniChip, s[dc])}>{call.decision}</span> : null}
            </span>
            <span className={s.switchFrame}>{h.frame}</span>
            {call ? (
              <span className={s.switchMeter} aria-label={`${call.confidence}% confidence`}>
                <span
                  className={cx(s.switchMeterFill, s[dc])}
                  style={{ width: `${Math.min(100, Math.max(0, call.confidence))}%` }}
                />
              </span>
            ) : null}
            {call ? <span className={s.switchConf}>{call.confidence}% sure</span> : null}
          </button>
        );
      })}
    </div>
  );
}

function ProbabilityGauge({ call }: { call: HorizonCall }) {
  const band = holdBand(call.band);
  const pUp = Math.min(1, Math.max(0, call.probability));
  return (
    <div className={s.gauge}>
      <div className={s.gaugeHead}>
        <span className={s.panelTitle}>Probability of an up-move</span>
        <span className={s.prob}>
          p(up) <strong>{Math.round(pUp * 100)}%</strong>
        </span>
      </div>
      <div
        className={s.gaugeTrack}
        role="meter"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pUp * 100)}
        aria-label="Probability of an up-move"
      >
        <span className={s.gaugeSell} />
        <span className={s.gaugeBuy} />
        {band ? (
          <span
            className={s.gaugeBand}
            style={{ left: `${band.low * 100}%`, width: `${(band.high - band.low) * 100}%` }}
            title="HOLD band"
          />
        ) : null}
        <span className={s.gaugeMid} />
        <span
          className={cx(s.gaugeMarker, s[decisionClass(call.decision)])}
          style={{ left: `${pUp * 100}%` }}
        />
      </div>
      <div className={s.gaugeScale}>
        <span>SELL</span>
        <span>{band ? 'HOLD' : '50%'}</span>
        <span>BUY</span>
      </div>
      {band ? <p className={s.gaugeNote}>{bandExplainer(pUp, band)}</p> : null}
    </div>
  );
}

function DriverBars({ call }: { call: HorizonCall }) {
  const factors = call.factors ?? [];
  if (factors.length === 0) {
    // Payloads cached before driver impacts existed carry names only.
    return (
      <div className={s.drivers}>
        <span className={s.panelTitle}>What&apos;s moving this call</span>
        {call.drivers.length > 0 ? (
          <div className={s.driverChips}>
            {call.drivers.map((name) => (
              <span key={name} className={s.driverChip}>
                {driverLabel(name)}
              </span>
            ))}
          </div>
        ) : (
          <p className={s.driversEmpty}>
            Too little data to attribute this call to specific drivers.
          </p>
        )}
      </div>
    );
  }

  const peak = Math.max(...factors.map((factor) => Math.abs(factor.impact)), 1e-9);
  return (
    <div className={s.drivers}>
      <div className={s.driversHead}>
        <span className={s.panelTitle}>What&apos;s moving this call</span>
        <span className={s.driverLegend}>
          <i className={s.legendUp} aria-hidden="true" /> pushes up
          <i className={s.legendDown} aria-hidden="true" /> pushes down
        </span>
      </div>
      <ul className={s.driverList}>
        {factors.map((factor) => {
          const up = factor.impact >= 0;
          const width = (Math.abs(factor.impact) / peak) * 50;
          return (
            <li key={factor.name} className={s.driverRow}>
              <span className={s.driverName}>
                {driverLabel(factor.name)}
                <span className={s.driverHint}>{driverHint(factor.name)}</span>
              </span>
              <span className={s.driverTrack} aria-hidden="true">
                <span className={s.driverAxis} />
                <span
                  className={cx(s.driverFill, up ? s.up : s.down)}
                  style={
                    up ? { left: '50%', width: `${width}%` } : { right: '50%', width: `${width}%` }
                  }
                />
              </span>
              <span className={cx(s.driverValue, up ? s.upText : s.downText)}>
                {up ? '+' : '−'}
                {Math.abs(factor.impact).toFixed(2)}
              </span>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function AskHella({
  symbol,
  decision,
  horizon
}: {
  symbol: string;
  decision: Decision;
  horizon: Horizon;
}) {
  const span = HORIZON_SHORT[horizon];
  const questions = [
    `Why is ${symbol} ${decision} on the ${span} horizon?`,
    decision === 'HOLD'
      ? `What would turn ${symbol} into a BUY or SELL ${span}?`
      : `What would invalidate the ${span} ${decision} on ${symbol}?`,
    `Which level matters most for ${symbol} right now?`
  ];
  return (
    <div className={s.ask}>
      <span className={s.panelTitle}>Ask {AGENT_NAME}</span>
      <div className={s.askRow}>
        {questions.map((question) => (
          <Link
            key={question}
            className={s.askChip}
            to={`/ai-console/agent?${new URLSearchParams({ symbol, q: question }).toString()}`}
          >
            {question}
          </Link>
        ))}
      </div>
    </div>
  );
}

function ConfidenceRing({ value, decision }: { value: number; decision: Decision }) {
  const r = 30;
  const c = 2 * Math.PI * r;
  const offset = c * (1 - Math.min(100, Math.max(0, value)) / 100);
  return (
    <svg className={s.ring} viewBox="0 0 76 76" role="img" aria-label={`${value}% confidence`}>
      <circle className={s.ringTrack} cx="38" cy="38" r={r} />
      <circle
        className={cx(s.ringFill, s[decisionClass(decision)])}
        cx="38"
        cy="38"
        r={r}
        strokeDasharray={c}
        strokeDashoffset={offset}
      />
      <text className={s.ringText} x="38" y="40">
        {value}
      </text>
      <text className={s.ringUnit} x="38" y="52">
        % sure
      </text>
    </svg>
  );
}

/* -- Right column ---------------------------------------------------------- */

function LevelsPanel({ levels }: { levels: Levels }) {
  const pct = spotPositionPct(levels.support, levels.resistance, levels.spot);
  const ladder = levelLadder(levels);
  return (
    <div className={s.panel}>
      <p className={s.panelTitle}>Levels</p>
      {pct != null ? (
        <div className={s.posWrap}>
          <div className={s.posEnds}>
            <div className={s.posEnd}>
              <span className={s.posEndKey}>Support</span>
              <span className={s.posEndVal}>{fmtPrice(levels.support)}</span>
            </div>
            <div className={cx(s.posEnd, s.right)}>
              <span className={s.posEndKey}>Resistance</span>
              <span className={s.posEndVal}>{fmtPrice(levels.resistance)}</span>
            </div>
          </div>
          <div className={s.posTrack}>
            <span
              className={cx(s.posSpot, pct >= 85 ? s.atEnd : pct <= 15 ? s.atStart : undefined)}
              // Keep the 14px dot fully on the track even at the extremes.
              style={{ left: `${Math.min(96, Math.max(4, pct))}%` }}
            >
              <span className={s.posSpotVal}>{fmtPrice(levels.spot)}</span>
            </span>
          </div>
        </div>
      ) : null}

      <table className={s.ladder}>
        <caption className={s.srOnly}>
          Levels from highest to lowest, with distance from spot
        </caption>
        <thead>
          <tr>
            <th scope="col">Level</th>
            <th scope="col" className={s.num}>
              Price
            </th>
            <th scope="col" className={s.num}>
              From spot
            </th>
          </tr>
        </thead>
        <tbody>
          {ladder.map((row) => (
            <tr
              key={row.key}
              className={cx(
                row.side === 'spot' && s.ladderSpot,
                row.nearest && s.ladderNearest,
                row.side === 'above' && s.ladderAbove,
                row.side === 'below' && s.ladderBelow
              )}
            >
              <th scope="row">
                {row.label}
                {row.nearest ? <span className={s.nearestTag}>nearest</span> : null}
              </th>
              <td className={s.num}>{fmtPrice(row.price)}</td>
              <td className={s.num}>
                {row.side === 'spot'
                  ? '—'
                  : `${row.points > 0 ? '+' : '−'}${fmtPrice(Math.abs(row.points))} (${Math.abs(
                      row.percent
                    ).toFixed(2)}%)`}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ScaffoldPanel({
  scaffold,
  actionable,
  decision
}: {
  scaffold: Scaffold;
  actionable: boolean;
  decision: Decision;
}) {
  const points = scaffoldPoints(scaffold);
  const empty = scaffold.entry == null && scaffold.stop == null && scaffold.target == null;
  return (
    <div className={s.panel}>
      <p className={s.panelTitle}>Trade scaffold</p>
      {empty ? (
        <p className={s.emptyState}>
          {decision === 'HOLD'
            ? `No set-up while the intraday call is HOLD. ${AGENT_NAME} drafts an entry, stop and target once a horizon turns decisive.`
            : 'No set-up could be drawn from the current levels.'}
        </p>
      ) : (
        <>
          <div className={s.statGrid}>
            <Stat label="Entry" value={fmtPrice(scaffold.entry)} />
            <Stat
              label="Stop"
              value={fmtPrice(scaffold.stop)}
              tone="neg"
              note={points ? `risk ${fmtPrice(points.risk)} pts` : undefined}
            />
            <Stat
              label="Target"
              value={fmtPrice(scaffold.target)}
              tone="pos"
              note={points ? `reward ${fmtPrice(points.reward)} pts` : undefined}
            />
            <Stat label="R : R" value={fmtRatio(scaffold.risk_reward)} />
          </div>
          {scaffold.suggested_contract ? (
            <p className={s.contract}>{scaffold.suggested_contract}</p>
          ) : null}
        </>
      )}
      <p className={s.illustrative}>
        {actionable
          ? 'Illustrative — the app places no orders.'
          : 'Illustrative only — built on simulated data, not tradeable.'}
      </p>
    </div>
  );
}

function Stat({
  label,
  value,
  tone,
  note
}: {
  label: string;
  value: string;
  tone?: 'pos' | 'neg';
  note?: string | undefined;
}) {
  return (
    <div className={s.stat}>
      <span className={s.statKey}>{label}</span>
      <span className={cx(s.statVal, tone ? s[tone] : undefined)}>{value}</span>
      {note ? <span className={s.statNote}>{note}</span> : null}
    </div>
  );
}

function HistoryPanel({ symbol }: { symbol: string }) {
  const history = useGuidanceHistoryQuery(symbol, 20);
  const items = history.data?.items ?? [];
  const today = items.filter((item) => isTodayIST(item.generated_at));
  const shown = (today.length ? today : items).slice(0, 8);

  return (
    <div className={s.panel}>
      <div className={s.historyHead}>
        <p className={s.panelTitle}>Call changes</p>
        <span className={s.historyScope}>{today.length ? 'today, intraday' : 'latest'}</span>
      </div>
      {history.isLoading ? (
        <p className={s.emptyState}>Loading…</p>
      ) : shown.length === 0 ? (
        <p className={s.emptyState}>No call changes recorded yet.</p>
      ) : (
        <ol className={s.timeline}>
          {shown.map((item, index) => {
            const previous = shown[index + 1];
            const dc = decisionClass(item.decision);
            return (
              <li key={`${item.generated_at}-${index}`} className={s.timelineRow}>
                <span className={s.timelineTime}>
                  {today.length ? timeIST(item.generated_at) : item.generated_at.slice(5, 10)}
                </span>
                <span className={cx(s.timelineDot, s[dc])} aria-hidden="true" />
                <span className={s.timelineText}>
                  {previous ? (
                    <>
                      <span className={s.timelineFrom}>{previous.decision}</span> →{' '}
                    </>
                  ) : null}
                  <strong className={cx(s.timelineTo, s[dc])}>{item.decision}</strong>{' '}
                  <span className={s.timelineConf}>{item.confidence}%</span>
                </span>
              </li>
            );
          })}
        </ol>
      )}
      {!today.length && shown.length ? (
        <p className={s.historyNote}>No change today — showing the most recent calls.</p>
      ) : null}
    </div>
  );
}

function StatusBar({ provenance }: { provenance: Guidance['provenance'] }) {
  const status = marketStatusIST();
  const sourceLabel =
    provenance === 'live'
      ? 'Live broker data'
      : provenance === 'cached'
        ? 'Cached broker data'
        : 'Simulated data';
  return (
    <footer className={s.statusBar}>
      <div className={s.statusRow}>
        <span className={s.statusItem}>
          Market
          <span className={cx(s.dot, status.open ? s.open : s.closed)} />
          <strong>{status.label}</strong>
        </span>
        <span className={s.statusCenter}>As of {nowLabelIST()}</span>
        <span className={s.statusItem}>🛡 {sourceLabel}</span>
      </div>
      <p className={s.disclaimer}>{DISCLAIMER}</p>
    </footer>
  );
}
