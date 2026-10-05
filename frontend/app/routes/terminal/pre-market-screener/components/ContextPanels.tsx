import type {
  Breadth,
  Flows,
  GlobalCues,
  OptionsPositioning,
  Technicals,
  Volatility
} from '$contexts/pre-market/types';
import { cx } from '$shared/ui/cx';
import { fmtChange, fmtLevel, fmtOne, fmtOutOf, fmtPercent, toNumber, tone } from '../pms-data';
import s from './ContextPanels.module.css';

/** One label/value pair. `null` renders a dash, never a zero. */
function Cell({
  label,
  value,
  toneOf,
  sub
}: {
  label: string;
  value: string;
  // `| undefined` explicitly: exactOptionalPropertyTypes distinguishes "absent"
  // from "present and undefined", and every caller here computes these.
  toneOf?: 'up' | 'down' | null | undefined;
  sub?: string | undefined;
}) {
  return (
    <div className={s.cell}>
      <dt>{label}</dt>
      <dd className={cx('cn-numeric', toneOf ? s[toneOf] : undefined)}>
        {value}
        {sub ? <span className={s.sub}>{sub}</span> : null}
      </dd>
    </div>
  );
}

/** Where the index sits on its own daily chart. */
export function TechnicalsGrid({ read }: { read: Technicals }) {
  const stack =
    read.ema_stacked_up === null
      ? 'Mixed'
      : read.ema_stacked_up
        ? 'Rising (20>50>100>200)'
        : 'Falling (20<50<100<200)';

  return (
    <dl className={s.grid}>
      <Cell label="EMA 20" value={fmtLevel(read.ema20)} />
      <Cell label="EMA 50" value={fmtLevel(read.ema50)} />
      <Cell label="EMA 100" value={fmtLevel(read.ema100)} />
      <Cell label="EMA 200" value={fmtLevel(read.ema200)} />
      {/* "Mixed" is a real state, not a missing one: the averages disagreeing
          is precisely when a trend read is least entitled to pick a side. */}
      <Cell
        label="Stack"
        value={stack}
        toneOf={read.ema_stacked_up === null ? null : read.ema_stacked_up ? 'up' : 'down'}
      />
      <Cell label="RSI 14" value={fmtOne(read.rsi14)} />
      <Cell
        label="ADX 14"
        value={fmtOne(read.adx14)}
        sub={read.adx14 !== null && read.adx14 < 20 ? 'Range, not trend' : undefined}
      />
      <Cell
        label="ATR 14"
        value={fmtLevel(read.atr14)}
        sub={read.atr_percent !== null ? `${read.atr_percent.toFixed(2)}% of spot` : undefined}
      />
    </dl>
  );
}

/** India VIX and the chain's own implied volatility. */
export function VolatilityCard({ read }: { read: Volatility }) {
  return (
    <>
      <dl className={s.grid}>
        <Cell label="India VIX" value={fmtLevel(read.india_vix)} />
        <Cell
          label="VIX change"
          value={fmtPercent(read.india_vix_change_percent)}
          toneOf={tone(read.india_vix_change_percent)}
        />
        <Cell label="ATM IV" value={read.atm_iv === null ? '—' : `${fmtLevel(read.atm_iv)}%`} />
        <Cell label="IV percentile" value={fmtLevel(read.iv_percentile)} />
      </dl>
      {/* The sample size travels with the rank, always — it is why the rank
          may be blank, and eleven sessions cannot support a percentile. */}
      <p className={s.footnote}>
        {read.vix_percentile === null
          ? `VIX percentile needs more history — ${read.vix_sample_sessions} sessions stored so far.`
          : `VIX percentile ${fmtOne(read.vix_percentile)} over ${read.vix_sample_sessions} sessions.`}
      </p>
    </>
  );
}

/** Option positioning — where the book sits, not where price must go. */
export function OptionsCard({ read }: { read: OptionsPositioning }) {
  return (
    <>
      <dl className={s.grid}>
        <Cell label="PCR (OI)" value={fmtLevel(read.pcr_oi)} />
        <Cell
          label="PCR change"
          value={fmtChange(read.pcr_change)}
          toneOf={tone(read.pcr_change)}
        />
        <Cell label="ATM strike" value={fmtLevel(read.atm_strike)} />
        <Cell label="Max pain" value={fmtLevel(read.max_pain)} />
        <Cell label="Heaviest call OI" value={fmtLevel(read.call_wall)} />
        <Cell label="Heaviest put OI" value={fmtLevel(read.put_wall)} />
        <Cell label="ATM straddle" value={fmtLevel(read.atm_straddle)} />
        <Cell
          label="Days to expiry"
          value={read.days_to_expiry === null ? '—' : String(read.days_to_expiry)}
        />
      </dl>
      <p className={s.footnote}>
        The heaviest strikes are where positioning sits, not levels that will hold. Max pain is a
        pin-risk statistic near expiry and close to noise away from it.
      </p>
    </>
  );
}

/** What the world did overnight, and what GIFT is quoting off it. */
export function GlobalCard({ read }: { read: GlobalCues }) {
  const gift = read.gift;

  return (
    <>
      <dl className={s.grid}>
        <Cell
          label="Overnight pressure"
          value={fmtOne(toNumber(read.pressure_score))}
          toneOf={tone(read.pressure_score)}
          sub={read.pressure_band ?? undefined}
        />
        <Cell label="GIFT level" value={fmtLevel(gift?.level)} />
        <Cell
          label="GIFT day change"
          value={`${fmtChange(gift?.change)} (${fmtPercent(gift?.change_percent)})`}
          toneOf={tone(gift?.change)}
        />
        <Cell
          label="Overnight range"
          value={
            gift?.overnight_low && gift?.overnight_high
              ? `${fmtLevel(gift.overnight_low)} — ${fmtLevel(gift.overnight_high)}`
              : '—'
          }
        />
      </dl>

      {read.macro.length ? (
        <dl className={s.grid}>
          {read.macro.map((row) => (
            <Cell
              key={row.key}
              label={row.label}
              value={fmtPercent(row.change_percent)}
              toneOf={tone(row.change_percent)}
            />
          ))}
        </dl>
      ) : null}

      {/* A composite built from four of nine inputs is a different claim from
          one built on all nine, so the misses are named rather than dropped. */}
      {read.missing.length ? (
        <p className={s.footnote}>
          The composite is built without {read.missing.join(', ')} — no quote came back for{' '}
          {read.missing.length === 1 ? 'it' : 'them'}.
        </p>
      ) : null}
    </>
  );
}

/** Participation, always with its denominator. */
export function BreadthCard({ read }: { read: Breadth }) {
  const total = (read.advances ?? 0) + (read.declines ?? 0);
  const ratio =
    read.advances !== null && read.declines !== null && read.declines > 0
      ? read.advances / read.declines
      : null;

  return (
    <>
      <dl className={s.grid}>
        <Cell label="Advancing" value={fmtOutOf(read.advances, read.priced)} toneOf="up" />
        <Cell label="Declining" value={fmtOutOf(read.declines, read.priced)} toneOf="down" />
        <Cell label="Unchanged" value={read.unchanged === null ? '—' : String(read.unchanged)} />
        <Cell label="A/D ratio" value={ratio === null ? '—' : ratio.toFixed(2)} />
      </dl>
      {/* Counts, not a bare percentage: twelve BANK NIFTY members move a
          percentage in 8.3% steps, which reads as precision it does not have. */}
      <p className={s.footnote}>
        {read.priced !== null && read.universe !== null && read.priced < read.universe
          ? `${read.priced} of ${read.universe} members priced — the rest had no quote.`
          : `Across ${total || read.priced || 0} priced members.`}
      </p>
    </>
  );
}

/** Yesterday's institutional net, in rupees crore. */
export function FlowsCard({ read }: { read: Flows }) {
  return (
    <>
      <dl className={s.grid}>
        <Cell label="FII net" value={fmtChange(read.fii_net)} toneOf={tone(read.fii_net)} />
        <Cell label="DII net" value={fmtChange(read.dii_net)} toneOf={tone(read.dii_net)} />
      </dl>
      <p className={s.footnote}>
        Cash segment, ₹ crore{read.session_date ? ` · ${read.session_date}` : ''}. Published after
        the close, so this is the previous session.
      </p>
    </>
  );
}
