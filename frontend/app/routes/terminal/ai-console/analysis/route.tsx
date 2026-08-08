import { useState } from 'react';
import { useGuidanceQuery } from '$contexts/signals/queries';
import type { Decision, Guidance, Levels, Scaffold, SkillRead } from '$contexts/signals/types';
import { cx } from '$shared/ui/cx';
import DataSourceBadge from '$shared/ui/DataSourceBadge';
import {
  INSTRUMENTS,
  decisionClass,
  fmtPrice,
  fmtRatio,
  fmtScore,
  meterWidth,
  scoreLean,
  spotPositionPct
} from '../ai-console-data';
import ConsoleHeader from '../components/ConsoleHeader';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [
  { title: 'Nifty Analysis · AI Console · MarketCompass' }
];

/** The agent's name, shown throughout the console. */
const AGENT_NAME = 'Hella';

const DISCLAIMER =
  'Algorithmic signal derived from market data — not investment advice, and not a ' +
  'personalised recommendation to buy or sell any instrument. Levels and contracts are ' +
  'illustrative only.';

export default function NiftyAnalysis() {
  const [instIdx, setInstIdx] = useState(0);
  const instrument = INSTRUMENTS[instIdx] ?? INSTRUMENTS[0];

  const query = useGuidanceQuery(instrument.symbol);
  const guidance = query.data;

  return (
    <div className={s.page}>
      <ConsoleHeader
        title="Nifty Analysis"
        subtitle={
          <>
            The call, the skills behind it, the levels that matter and the risk — read by{' '}
            <strong>{AGENT_NAME}</strong>.
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
        <div className={s.layout}>
          <div className={s.column}>
            <GuidanceHeader guidance={guidance} />
            <SkillCards skills={guidance.skills} />
          </div>
          <div className={s.column}>
            <LevelsPanel levels={guidance.levels} />
            <ScaffoldPanel scaffold={guidance.scaffold} actionable={guidance.is_actionable} />
          </div>
        </div>
      )}
    </div>
  );
}

function GuidanceHeader({ guidance }: { guidance: Guidance }) {
  const dc = decisionClass(guidance.decision);
  const word =
    guidance.decision === 'BUY'
      ? 'leans bullish'
      : guidance.decision === 'SELL'
        ? 'leans bearish'
        : 'no clear edge';

  return (
    <div className={cx(s.panel, s.hero, s[dc])}>
      <div className={s.heroMain}>
        <div className={s.heroLeft}>
          <span className={cx(s.chip, s[dc])}>{guidance.decision}</span>
          <div>
            <div className={s.symbol}>{guidance.symbol}</div>
            <div className={s.decisionWord}>{word}</div>
          </div>
        </div>
        <ConfidenceRing value={guidance.confidence} decision={guidance.decision} />
      </div>

      <div className={s.provRow}>
        <DataSourceBadge source={guidance.provenance} />
      </div>

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

function SkillCards({ skills }: { skills: SkillRead[] }) {
  return (
    <div className={s.panel}>
      <p className={s.panelTitle}>Skill breakdown</p>
      <div className={s.skills}>
        {skills.map((skill) => {
          const lean = scoreLean(skill.score);
          return (
            <div key={skill.skill} className={cx(s.skill, s[lean])}>
              <div className={s.skillTop}>
                <span className={s.skillLabel}>{skill.label}</span>
                <span className={cx(s.scorePill, s[lean])}>{fmtScore(skill.score)}</span>
              </div>
              <span className={s.skillHeadline}>{skill.headline}</span>
              <div className={s.meter}>
                <span className={s.meterMid} />
                <span
                  className={cx(s.meterFill, s[lean])}
                  style={{ width: meterWidth(skill.score) }}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
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
            <span className={s.posSpot} style={{ left: `${pct}%` }}>
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
