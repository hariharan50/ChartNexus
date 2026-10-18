import { useMemo, useState } from 'react';
import Select from '$shared/ui/Select';
import { cx } from '$shared/ui/cx';
import type { OptionType } from '../calc/black-scholes';
import { type ChainRow, type EnrichedChain, type Leg, atmIndex, windowAround } from '../calc/chain';
import {
  EMPTY,
  fmtIndian,
  fmtIndianSigned,
  fmtPercent,
  fmtPrice,
  fmtSigned,
  tone
} from '../calc/format';
import s from '../stock-watch.module.css';

/** What the heat bars are scaled against. */
type Heat = 'oi' | 'oi_change' | 'volume' | 'none';

const HEAT_OPTIONS = [
  { value: 'oi' as const, label: 'Heat: open interest' },
  { value: 'oi_change' as const, label: 'Heat: change in OI' },
  { value: 'volume' as const, label: 'Heat: volume' },
  { value: 'none' as const, label: 'Heat: off' }
];

const SPAN_OPTIONS = [
  { value: '5', label: '±5 strikes' },
  { value: '10', label: '±10 strikes' },
  { value: '15', label: '±15 strikes' },
  { value: '20', label: '±20 strikes' },
  { value: 'all', label: 'All strikes' }
];

type SideFilter = 'both' | 'ce' | 'pe';

const SIDE_OPTIONS = [
  { value: 'both' as const, label: 'Calls & puts' },
  { value: 'ce' as const, label: 'Calls only' },
  { value: 'pe' as const, label: 'Puts only' }
];

/** Columns the reader can sort the ladder by, beyond the strike. */
type SortKey =
  'strike' | 'ce_oi' | 'pe_oi' | 'ce_oi_change' | 'pe_oi_change' | 'ce_volume' | 'pe_volume';

interface Props {
  chain: EnrichedChain;
  loading: boolean;
  /** Called when the reader picks a contract to plan or compare. */
  onPick: (strike: number, type: OptionType) => void;
  /** Strikes already on the comparison shortlist, for the toggle state. */
  shortlist: Set<string>;
  onShortlist: (strike: number, type: OptionType) => void;
}

function legValue(leg: Leg | undefined, heat: Heat): number {
  if (!leg) return 0;
  if (heat === 'oi') return leg.oi;
  if (heat === 'oi_change') return Math.abs(leg.oiChange);
  if (heat === 'volume') return leg.volume;
  return 0;
}

/**
 * The option chain, with CALLS on the left and PUTS on the right.
 *
 * Three things this table does that a plain dump of the payload does not:
 *
 * * **It separates quoted from computed.** `δ` is the broker's delta where the
 *   broker sent one; γ, θ and ν are always Black-Scholes off this leg's own
 *   IV, and the header says so. Mixing them in one column would let a reader
 *   hedge off an assumption believing it was an exchange figure.
 * * **It says when a row is hard to trade.** A wide spread, a thin book or no
 *   open interest gets a marker, because the attractive-looking premium on an
 *   untraded wing is attractive precisely because nobody will fill it.
 * * **It never prints a zero for silence.** A leg the feed did not quote shows
 *   a dash. The difference between "no bids" and "nothing said" is the
 *   difference between a trade and a mistake.
 */
export default function OptionChainTable({
  chain,
  loading,
  onPick,
  shortlist,
  onShortlist
}: Props) {
  const [span, setSpan] = useState('10');
  const [heat, setHeat] = useState<Heat>('oi');
  const [side, setSide] = useState<SideFilter>('both');
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({ key: 'strike', desc: false });

  const visible = useMemo(() => {
    const centre = atmIndex(chain.rows, chain.spot, chain.atmStrike);
    const windowed = windowAround(chain.rows, centre, span === 'all' ? 'all' : Number(span));
    if (sort.key === 'strike') {
      return sort.desc ? [...windowed].reverse() : windowed;
    }
    const read = (row: ChainRow): number => {
      switch (sort.key) {
        case 'ce_oi':
          return row.ce?.oi ?? -1;
        case 'pe_oi':
          return row.pe?.oi ?? -1;
        case 'ce_oi_change':
          return row.ce?.oiChange ?? 0;
        case 'pe_oi_change':
          return row.pe?.oiChange ?? 0;
        case 'ce_volume':
          return row.ce?.volume ?? -1;
        case 'pe_volume':
          return row.pe?.volume ?? -1;
        default:
          return row.strike;
      }
    };
    return [...windowed].sort((a, b) => (sort.desc ? read(b) - read(a) : read(a) - read(b)));
  }, [chain, span, sort]);

  const peak = useMemo(() => {
    let max = 0;
    for (const row of visible) {
      max = Math.max(max, legValue(row.ce, heat), legValue(row.pe, heat));
    }
    return max;
  }, [visible, heat]);

  const toggleSort = (key: SortKey) =>
    setSort((previous) =>
      previous.key === key ? { key, desc: !previous.desc } : { key, desc: true }
    );

  const showCalls = side !== 'pe';
  const showPuts = side !== 'ce';

  return (
    <section className={s.panel}>
      <div className={s.panelHead}>
        <div>
          <h2 className={s.panelTitle}>Option chain</h2>
          <p className={s.panelSub}>
            {chain.expiry} · {chain.daysToExpiry}d to expiry ·{' '}
            {chain.lotSize ? `lot ${chain.lotSize}` : 'lot size unknown'} · spot{' '}
            {fmtPrice(chain.spot)}
          </p>
        </div>
        <div className={s.panelActions}>
          <Select
            value={side}
            options={SIDE_OPTIONS}
            onChange={setSide}
            ariaLabel="Which sides to show"
            size="sm"
          />
          <Select
            value={span}
            options={SPAN_OPTIONS}
            onChange={setSpan}
            ariaLabel="Strike range"
            size="sm"
          />
          <Select
            value={heat}
            options={HEAT_OPTIONS}
            onChange={setHeat}
            ariaLabel="Heatmap column"
            size="sm"
            align="right"
          />
        </div>
      </div>

      {chain.greeksUnavailable ? (
        <p className={cx(s.notice, s.noticeWarn)} style={{ margin: 'var(--cn-space-3)' }}>
          <span>
            This chain carries no implied volatility, so γ, θ and ν cannot be computed for any leg.
            Delta is shown only where the broker quoted one.
          </span>
        </p>
      ) : null}

      <div className={s.panelBodyFlush}>
        {loading && chain.rows.length === 0 ? (
          <div className={s.skeleton} style={{ padding: 'var(--cn-space-4)' }} aria-hidden="true">
            <span className={s.skeletonRow} />
            <span className={s.skeletonRow} />
            <span className={s.skeletonRow} />
          </div>
        ) : chain.rows.length === 0 ? (
          <p className={s.empty}>No strikes quoted for this expiry.</p>
        ) : (
          <div className={s.tableScroll} style={{ maxHeight: '32rem', overflowY: 'auto' }}>
            <table className={s.table}>
              <thead>
                <tr>
                  {showCalls ? (
                    <>
                      <th className={s.left}>Build-up</th>
                      <th>δ</th>
                      <th>γ·θ·ν</th>
                      <th>IV</th>
                      <th className={s.sortable} onClick={() => toggleSort('ce_volume')}>
                        Vol
                      </th>
                      <th className={s.sortable} onClick={() => toggleSort('ce_oi_change')}>
                        ΔOI
                      </th>
                      <th className={s.sortable} onClick={() => toggleSort('ce_oi')}>
                        OI
                      </th>
                      <th>Bid×Qty</th>
                      <th>Ask×Qty</th>
                      <th>Chg%</th>
                      <th>LTP</th>
                    </>
                  ) : null}
                  <th className={s.sortable} onClick={() => toggleSort('strike')}>
                    Strike
                  </th>
                  {showPuts ? (
                    <>
                      <th>LTP</th>
                      <th>Chg%</th>
                      <th>Bid×Qty</th>
                      <th>Ask×Qty</th>
                      <th className={s.sortable} onClick={() => toggleSort('pe_oi')}>
                        OI
                      </th>
                      <th className={s.sortable} onClick={() => toggleSort('pe_oi_change')}>
                        ΔOI
                      </th>
                      <th className={s.sortable} onClick={() => toggleSort('pe_volume')}>
                        Vol
                      </th>
                      <th>IV</th>
                      <th>γ·θ·ν</th>
                      <th>δ</th>
                      <th className={s.left}>Build-up</th>
                    </>
                  ) : null}
                </tr>
              </thead>
              <tbody>
                {visible.map((row) => (
                  <tr key={row.strike} className={cx(row.atm && s.rowAtm)}>
                    {showCalls ? (
                      <CallCells
                        leg={row.ce}
                        strike={row.strike}
                        heat={heat}
                        peak={peak}
                        onPick={onPick}
                        onShortlist={onShortlist}
                        shortlisted={shortlist.has(`${row.strike}:CE`)}
                      />
                    ) : null}
                    <td className={s.strikeCell}>{fmtPrice(row.strike)}</td>
                    {showPuts ? (
                      <PutCells
                        leg={row.pe}
                        strike={row.strike}
                        heat={heat}
                        peak={peak}
                        onPick={onPick}
                        onShortlist={onShortlist}
                        shortlisted={shortlist.has(`${row.strike}:PE`)}
                      />
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <p className={s.notice} style={{ margin: 'var(--cn-space-3)' }}>
        <span>
          <strong>δ</strong> is the broker&apos;s own delta where it quoted one.{' '}
          <strong>γ·θ·ν</strong> are Black-Scholes, computed here from each leg&apos;s implied
          volatility at a 7% rate with no dividend and European exercise — NSE stock options are
          American-style, so they are an approximation, not a quote. A dash means the feed said
          nothing, which is not the same as zero.
        </span>
      </p>
    </section>
  );
}

interface CellProps {
  leg: Leg | undefined;
  strike: number;
  heat: Heat;
  peak: number;
  onPick: (strike: number, type: OptionType) => void;
  onShortlist: (strike: number, type: OptionType) => void;
  shortlisted: boolean;
}

function HeatCell({
  value,
  peak,
  side,
  children,
  className
}: {
  value: number;
  peak: number;
  side: 'call' | 'put';
  children: React.ReactNode;
  className?: string | undefined;
}) {
  const width = peak > 0 ? Math.min(100, (value / peak) * 100) : 0;
  return (
    <td className={cx(s.heat, side === 'call' ? s.heatCall : s.heatPut, className)}>
      {width > 0 ? (
        <span className={s.heatFill} style={{ width: `${width}%` }} aria-hidden="true" />
      ) : null}
      {children}
    </td>
  );
}

function greekTriplet(leg: Leg): string {
  if (!leg.modelGreeks) return EMPTY;
  const { gamma, theta, vega } = leg.modelGreeks;
  return `${gamma.toFixed(4)} · ${theta.toFixed(2)} · ${vega.toFixed(2)}`;
}

function book(price: number | undefined, qty: number | undefined): string {
  if (price == null) return EMPTY;
  return qty != null ? `${fmtPrice(price)}×${fmtIndian(qty)}` : fmtPrice(price);
}

function liquidityMark(leg: Leg): string {
  if (leg.liquidity.grade === 'illiquid') return '⚠';
  if (leg.liquidity.grade === 'thin') return '·';
  return '';
}

function BuildupCell({
  leg,
  onShortlist,
  strike,
  shortlisted
}: {
  leg: Leg | undefined;
  strike: number;
  onShortlist: (strike: number, type: OptionType) => void;
  shortlisted: boolean;
}) {
  if (!leg) {
    return <td className={cx(s.left, s.muted)}>{EMPTY}</td>;
  }
  const state = leg.buildup.state;
  const chipTone =
    state === 'long_buildup' || state === 'short_covering'
      ? s.chipUp
      : state === 'short_buildup' || state === 'long_unwinding'
        ? s.chipDown
        : s.chipNeutral;

  return (
    <td className={s.left}>
      <button
        type="button"
        className={cx(s.chip, chipTone)}
        title={`${leg.buildup.rule}${leg.liquidity.reasons.length ? `\n${leg.liquidity.reasons.join('\n')}` : ''}`}
        onClick={() => onShortlist(strike, leg.type)}
        aria-pressed={shortlisted}
        style={{ cursor: 'pointer', background: shortlisted ? 'var(--cn-accent-weak)' : undefined }}
      >
        {state === 'unknown'
          ? 'n/a'
          : state === 'neutral'
            ? '—'
            : state.replace('_', ' ').replace('buildup', 'build')}
        {liquidityMark(leg)}
      </button>
    </td>
  );
}

function CallCells({ leg, strike, heat, peak, onPick, onShortlist, shortlisted }: CellProps) {
  const itm = leg?.moneyness === 'ITM';
  const cell = itm ? s.itmCall : undefined;
  if (!leg) {
    return (
      <>
        <td className={cx(s.left, s.muted)}>{EMPTY}</td>
        {Array.from({ length: 10 }, (_, i) => (
          <td key={i} className={s.muted}>
            {EMPTY}
          </td>
        ))}
      </>
    );
  }
  return (
    <>
      <BuildupCell leg={leg} strike={strike} onShortlist={onShortlist} shortlisted={shortlisted} />
      <td className={cell}>{leg.quotedDelta != null ? leg.quotedDelta.toFixed(3) : EMPTY}</td>
      <td className={cx(cell, s.muted)}>{greekTriplet(leg)}</td>
      <td className={cell}>{leg.iv != null ? `${leg.iv.toFixed(1)}%` : EMPTY}</td>
      <HeatCell value={heat === 'volume' ? leg.volume : 0} peak={peak} side="call" className={cell}>
        {fmtIndian(leg.volume)}
      </HeatCell>
      <HeatCell
        value={heat === 'oi_change' ? Math.abs(leg.oiChange) : 0}
        peak={peak}
        side="call"
        className={cx(cell, tone(leg.oiChange) ? s[tone(leg.oiChange)!] : undefined)}
      >
        {fmtIndianSigned(leg.oiChange)}
      </HeatCell>
      <HeatCell value={heat === 'oi' ? leg.oi : 0} peak={peak} side="call" className={cell}>
        {fmtIndian(leg.oi)}
      </HeatCell>
      <td className={cell}>{book(leg.bid, leg.bidQty)}</td>
      <td className={cell}>{book(leg.ask, leg.askQty)}</td>
      <td className={cx(cell, tone(leg.changePercent) ? s[tone(leg.changePercent)!] : undefined)}>
        {fmtPercent(leg.changePercent)}
      </td>
      <td className={cell}>
        <button
          type="button"
          className={s.action}
          style={{ minHeight: 0, padding: '0 0.25rem', border: 0, background: 'none' }}
          onClick={() => onPick(strike, 'CE')}
          title={`Plan a long ${strike} CE — breakeven ${fmtPrice(leg.breakeven)}, time value ${fmtPrice(leg.extrinsic)}`}
        >
          {fmtPrice(leg.ltp)}
        </button>
      </td>
    </>
  );
}

function PutCells({ leg, strike, heat, peak, onPick, onShortlist, shortlisted }: CellProps) {
  const itm = leg?.moneyness === 'ITM';
  const cell = itm ? s.itmPut : undefined;
  if (!leg) {
    return (
      <>
        {Array.from({ length: 10 }, (_, i) => (
          <td key={i} className={s.muted}>
            {EMPTY}
          </td>
        ))}
        <td className={cx(s.left, s.muted)}>{EMPTY}</td>
      </>
    );
  }
  return (
    <>
      <td className={cell}>
        <button
          type="button"
          className={s.action}
          style={{ minHeight: 0, padding: '0 0.25rem', border: 0, background: 'none' }}
          onClick={() => onPick(strike, 'PE')}
          title={`Plan a long ${strike} PE — breakeven ${fmtPrice(leg.breakeven)}, time value ${fmtPrice(leg.extrinsic)}`}
        >
          {fmtPrice(leg.ltp)}
        </button>
      </td>
      <td className={cx(cell, tone(leg.changePercent) ? s[tone(leg.changePercent)!] : undefined)}>
        {fmtPercent(leg.changePercent)}
      </td>
      <td className={cell}>{book(leg.bid, leg.bidQty)}</td>
      <td className={cell}>{book(leg.ask, leg.askQty)}</td>
      <HeatCell value={heat === 'oi' ? leg.oi : 0} peak={peak} side="put" className={cell}>
        {fmtIndian(leg.oi)}
      </HeatCell>
      <HeatCell
        value={heat === 'oi_change' ? Math.abs(leg.oiChange) : 0}
        peak={peak}
        side="put"
        className={cx(cell, tone(leg.oiChange) ? s[tone(leg.oiChange)!] : undefined)}
      >
        {fmtIndianSigned(leg.oiChange)}
      </HeatCell>
      <HeatCell value={heat === 'volume' ? leg.volume : 0} peak={peak} side="put" className={cell}>
        {fmtIndian(leg.volume)}
      </HeatCell>
      <td className={cell}>{leg.iv != null ? `${leg.iv.toFixed(1)}%` : EMPTY}</td>
      <td className={cx(cell, s.muted)}>{greekTriplet(leg)}</td>
      <td className={cell}>{leg.quotedDelta != null ? leg.quotedDelta.toFixed(3) : EMPTY}</td>
      <BuildupCell leg={leg} strike={strike} onShortlist={onShortlist} shortlisted={shortlisted} />
    </>
  );
}

export { fmtSigned };
