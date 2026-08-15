import { useState } from 'react';
import { useGuidanceQuery } from '$contexts/signals/queries';
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
  biasPhrase,
  confidenceBand,
  decisionClass,
  driverLabel,
  fmtPrice,
  fmtRatio,
  marketStatusIST,
  nowLabelIST,
  pcrSentiment,
  regimeLabel,
  spotPositionPct,
  vixAbsoluteChange,
  vixEnvironment
} from '../ai-console-data';
import ConsoleHeader from '../components/ConsoleHeader';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [
  { title: 'Market Analysis · AI Console · MarketCompass' }
];

/** The agent's name, shown throughout the console. */
const AGENT_NAME = 'Hella';

const DISCLAIMER =
  'Algorithmic signal derived from market data — not investment advice, and not a ' +
  'personalised recommendation to buy or sell any instrument. Levels and contracts are ' +
  'illustrative only.';

export default function NiftyAnalysis() {
  const [instIdx, setInstIdx] = useState(0);
  const [horizon, setHorizon] = useState<Horizon>('intraday');
  const instrument = INSTRUMENTS[instIdx] ?? INSTRUMENTS[0];

  const query = useGuidanceQuery(instrument.symbol);
  const guidance = query.data;

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
      />

      {query.isLoading && !guidance ? (
        <div className={s.panel}>
          <div className={s.state}>{AGENT_NAME} is reading the tape…</div>
        </div>
      ) : query.isError || !guidance ? (
        <div className={s.panel}>
          <div className={s.state}>Guidance is unavailable for {instrument.symbol} right now.</div>
        </div>
      ) : (
        <>
          <ContextCards guidance={guidance} />
          <div className={s.layout}>
            <div className={s.column}>
              <GuidanceHeader guidance={guidance} horizon={horizon} onHorizon={setHorizon} />
            </div>
            <div className={s.column}>
              <LevelsPanel levels={guidance.levels} />
              <ScaffoldPanel scaffold={guidance.scaffold} actionable={guidance.is_actionable} />
            </div>
          </div>
          <StatusBar provenance={guidance.provenance} />
        </>
      )}
    </div>
  );
}

function ContextCards({ guidance }: { guidance: Guidance }) {
  const headline = guidance.horizons.find((c) => c.horizon === 'intraday') ?? guidance.horizons[0];
  const confidence = headline?.confidence ?? guidance.confidence;
  const decision = headline?.decision ?? guidance.decision;

  const vix = guidance.context.india_vix;
  const vixPct = guidance.context.india_vix_change_percent;
  const vixAbs = vixAbsoluteChange(vix, vixPct);
  const env = vixEnvironment(vix);
  const pcr = guidance.context.pcr;
  const pcrRead = pcrSentiment(pcr);
  // A falling VIX (calmer market) reads positive; rising is the risk-on warning.
  const vixTone = vixPct == null ? 'flat' : vixPct < 0 ? 'pos' : vixPct > 0 ? 'neg' : 'flat';

  const vixArrow = vixPct == null || vixPct === 0 ? '' : vixPct < 0 ? '▼ ' : '▲ ';

  return (
    <div className={s.cards}>
      <div className={cx(s.card, s.tinted, s.cardBlue)}>
        <span className={s.cardTitle}>✦ AI Confidence</span>
        <span className={s.cardBig}>{confidence}%</span>
        <span className={s.cardSub}>{confidenceBand(confidence)}</span>
        <div className={s.certainty}>
          <span className={s.certaintyLabel}>Model certainty</span>
          <div className={s.certaintyTrack}>
            <span
              className={s.certaintyFill}
              style={{ width: `${Math.min(100, Math.max(0, confidence))}%` }}
            />
          </div>
        </div>
      </div>

      <div className={cx(s.card, s.tinted, s.cardRed)}>
        <span className={s.cardTitle}>⧉ Market Regime</span>
        <span className={s.cardRegime}>{regimeLabel(guidance.regime)}</span>
        <span className={s.cardSub}>{biasPhrase(decision)}</span>
        <span className={s.pill}>{env.label}</span>
      </div>

      <div className={cx(s.card, s.tinted, s.cardPink)}>
        <span className={s.cardTitle}>⟁ Volatility (India VIX)</span>
        <span className={s.cardBig}>{vix == null ? '—' : vix.toFixed(2)}</span>
        {vixAbs != null && vixPct != null ? (
          <span className={cx(s.cardDelta, s[vixTone])}>
            {vixArrow}
            {vixAbs > 0 ? '+' : ''}
            {vixAbs.toFixed(2)} ({vixPct > 0 ? '+' : ''}
            {vixPct.toFixed(1)}%)
          </span>
        ) : (
          <span className={s.cardSub}>No change data</span>
        )}
        <span className={s.cardNote}>{env.note}</span>
      </div>

      <div className={cx(s.card, s.tinted, s.cardLavender)}>
        <span className={s.cardTitle}>◪ PCR (Total)</span>
        <span className={s.cardBig}>{pcr == null ? '—' : pcr.toFixed(2)}</span>
        <span className={s.cardSub}>{pcrRead.label}</span>
        <span className={s.cardNote}>{pcrRead.note}</span>
      </div>
    </div>
  );
}

function StatusBar({ provenance }: { provenance: Guidance['provenance'] }) {
  const status = marketStatusIST();
  const sourceLabel =
    provenance === 'live'
      ? 'Data by NSE'
      : provenance === 'cached'
        ? 'Cached data'
        : 'Simulated data';
  return (
    <div className={s.statusBar}>
      <span className={s.statusItem}>
        Market Status
        <span className={cx(s.dot, status.open ? s.open : s.closed)} />
        <strong>{status.label}</strong>
      </span>
      <span className={s.statusCenter}>As of {nowLabelIST()}</span>
      <span className={s.statusItem}>🛡 {sourceLabel}</span>
    </div>
  );
}

/** The selected horizon's call, or the intraday headline as a fallback. */
function callFor(guidance: Guidance, horizon: Horizon): HorizonCall | undefined {
  return (
    guidance.horizons.find((c) => c.horizon === horizon) ??
    guidance.horizons.find((c) => c.horizon === 'intraday') ??
    guidance.horizons[0]
  );
}

function GuidanceHeader({
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

  return (
    <div className={cx(s.panel, s.hero, s[dc])}>
      <div className={s.heroTop}>
        <span className={cx(s.regime, s[dc])}>{regimeLabel(guidance.regime)}</span>
        <DataSourceBadge source={guidance.provenance} />
      </div>

      <div className={s.switcher} role="tablist" aria-label="Signal horizon">
        {HORIZONS.map((h) => (
          <button
            key={h.key}
            type="button"
            role="tab"
            aria-selected={h.key === horizon}
            className={cx(s.switchBtn, h.key === horizon && s.switchOn)}
            onClick={() => onHorizon(h.key)}
          >
            <span className={s.switchLabel}>{h.label}</span>
            <span className={s.switchFrame}>{h.frame}</span>
          </button>
        ))}
      </div>

      <div className={s.heroMain}>
        <div className={s.heroLeft}>
          <span className={cx(s.chip, s[dc])}>{decision}</span>
          <div>
            <div className={s.symbol}>{guidance.symbol}</div>
            <div className={s.decisionWord}>{word}</div>
          </div>
        </div>
        <ConfidenceRing value={confidence} decision={decision} />
      </div>

      {call ? <DriverList call={call} /> : null}

      <p className={s.rationale}>{guidance.rationale}</p>

      {guidance.warnings.map((warning) => (
        <p key={warning} className={s.warning}>
          ⚠ {warning}
        </p>
      ))}
      <p className={s.disclaimer}>{DISCLAIMER}</p>
    </div>
  );
}

function DriverList({ call }: { call: HorizonCall }) {
  const pUp = Math.round(call.probability * 100);
  return (
    <div className={s.drivers}>
      <div className={s.driversHead}>
        <span className={s.panelTitle}>What's moving this call</span>
        <span className={s.prob}>
          p(up) <strong>{pUp}%</strong>
        </span>
      </div>
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

function LevelsPanel({ levels }: { levels: Levels }) {
  const pct = spotPositionPct(levels.support, levels.resistance, levels.spot);
  const chips: Array<[string, number | null]> = [
    ['Max pain', levels.max_pain],
    ['Gamma flip', levels.gamma_flip],
    ['Call wall', levels.call_wall],
    ['Put wall', levels.put_wall]
  ];
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
            <span className={s.posFill} style={{ width: `${pct}%` }} />
            <span
              className={cx(s.posSpot, pct >= 85 ? s.atEnd : pct <= 15 ? s.atStart : undefined)}
              // Keep the 14px dot fully on the track even at the extremes.
              style={{ left: `${Math.min(96, Math.max(4, pct))}%` }}
            >
              <span className={s.posSpotVal}>{fmtPrice(levels.spot)}</span>
            </span>
          </div>
        </div>
      ) : (
        <div className={s.row}>
          <span className={s.rowKey}>Spot</span>
          <span className={s.rowVal}>{fmtPrice(levels.spot)}</span>
        </div>
      )}

      <div className={s.chipsRow}>
        {chips.map(([key, value]) => (
          <div key={key} className={s.levelChip}>
            <span className={s.levelKey}>{key}</span>
            <span className={s.levelVal}>{fmtPrice(value)}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ScaffoldPanel({ scaffold, actionable }: { scaffold: Scaffold; actionable: boolean }) {
  return (
    <div className={s.panel}>
      <p className={s.panelTitle}>Trade scaffold</p>
      <div className={s.statGrid}>
        <Stat label="Entry" value={fmtPrice(scaffold.entry)} />
        <Stat label="Stop" value={fmtPrice(scaffold.stop)} tone="neg" />
        <Stat label="Target" value={fmtPrice(scaffold.target)} tone="pos" />
        <Stat label="R : R" value={fmtRatio(scaffold.risk_reward)} />
      </div>
      {scaffold.suggested_contract ? (
        <p className={s.contract}>{scaffold.suggested_contract}</p>
      ) : null}
      <p className={s.illustrative}>
        {actionable
          ? 'Illustrative — the app places no orders.'
          : 'Illustrative only — built on simulated data, not tradeable.'}
      </p>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'pos' | 'neg' }) {
  return (
    <div className={s.stat}>
      <span className={s.statKey}>{label}</span>
      <span className={cx(s.statVal, tone ? s[tone] : undefined)}>{value}</span>
    </div>
  );
}
