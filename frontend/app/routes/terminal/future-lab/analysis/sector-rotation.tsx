import { useMemo, useState } from 'react';
import {
  DEFAULT_INDEX,
  DEFAULT_RRG_INTERVAL,
  DEFAULT_RRG_TAIL,
  RRG_INTERVALS,
  type IndexId,
  type RrgInterval
} from '$contexts/market-breadth/api';
import { useSectorRrgQuery } from '$contexts/market-breadth/queries';
import type { RrgQuadrant, RrgTail } from '$contexts/market-breadth/types';
import EChart from '$shared/charts/EChart';
import { buildSectorRrgOption, type RrgSeries } from '$shared/charts/options/sector-rrg';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { cx } from '$shared/ui/cx';
import IconScatter from '$shared/ui/icons/IconScatter';
import { SessionStatus } from '../components/SessionHeader';
import { INDEX_REFRESH_SECONDS, QUADRANTS, quadrantMeta } from './analysis-data';
import { AnalysisHead, IndexPicker, SourceBadge } from './components/AnalysisHead';
import s from './analysis.module.css';
import r from './sector-rotation.module.css';
import type { Route } from './+types/sector-rotation';

export const meta: Route.MetaFunction = () => [
  { title: 'Sector Rotation · Future Lab · ChartNexus' }
];

/** Tail lengths the stepper walks between. */
const TAIL_MIN = 3;
const TAIL_MAX = 20;

/** Border-colour class per quadrant, so every surface agrees with the plot. */
const QUADRANT_CLASS: Record<RrgQuadrant, string> = {
  leading: r.leading!,
  improving: r.improving!,
  weakening: r.weakening!,
  lagging: r.lagging!
};

/**
 * Sector Rotation, as a Relative Rotation Graph.
 *
 * **This page used to say an RRG was impossible here, and it was right at the
 * time.** It plotted one session's strength against *participation* — the
 * share of a sector's members advancing — because a momentum axis needs weeks
 * of stored history and nothing stored it. What changed is not the arithmetic
 * but the archive: the futures board is captured minute by minute for the
 * whole F&O universe, which is a genuine multi-period price history for every
 * constituent, and `/breadth/sector-rotation/rrg` reads it.
 *
 * So both axes are now the real thing — RS-Ratio against RS-Momentum, each a
 * z-score centred on 100 — and every sector carries a tail through the
 * quadrants rather than a single dot.
 *
 * **What the archive's depth still costs.** The capture worker keeps thirty
 * sessions, so the daily axis cannot fill its window until thirteen have been
 * captured, and the intraday axes get there in two. The board says which of
 * those it is rather than showing one blank "no data" for both — "24 of 35
 * periods" and "no sector could be priced" are different problems with
 * different fixes, and a reader who cannot tell them apart will go looking in
 * the wrong place.
 */
export default function SectorRotation() {
  const [index, setIndex] = useState<IndexId>(DEFAULT_INDEX);
  const [interval, setInterval] = useState<RrgInterval>(DEFAULT_RRG_INTERVAL);
  const [tail, setTail] = useState(DEFAULT_RRG_TAIL);
  const [labels, setLabels] = useState(true);
  // Which sectors are plotted. Empty means "all": the page starts with
  // everything on, and the set only fills once the reader hides something, so
  // a sector that appears after a refresh is visible rather than silently off.
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());

  const theme = useChartTheme();
  const rrg = useSectorRrgQuery(index, interval, tail);
  const data = rrg.data;

  const tails = useMemo(() => data?.tails ?? [], [data]);
  const shown = useMemo(() => tails.filter((entry) => !hidden.has(entry.sector)), [tails, hidden]);

  const series = useMemo<RrgSeries[]>(
    () =>
      shown.map((entry) => ({
        sector: entry.sector,
        quadrant: entry.quadrant,
        measured: entry.measured,
        members: entry.members,
        points: entry.points.map((point) => ({
          at: point.at,
          x: point.rs_ratio,
          y: point.rs_momentum
        }))
      })),
    [shown]
  );

  const option = useMemo(
    () => buildSectorRrgOption(series, theme, { labels, formatStamp }),
    [series, theme, labels]
  );

  const toggle = (sector: string) =>
    setHidden((current) => {
      const next = new Set(current);
      if (!next.delete(sector)) next.add(sector);
      return next;
    });

  const filling = data !== undefined && data.periods < data.periods_required;

  return (
    <div className={s.page}>
      <AnalysisHead
        icon={<IconScatter />}
        title="Sector Rotation"
        subtitle={`Relative Rotation Graph · every sector against ${data?.benchmark ?? 'the index'}`}
      >
        <IndexPicker value={index} onChange={setIndex} />
        <SourceBadge source={data?.source} />
        <SessionStatus
          intervalSeconds={INDEX_REFRESH_SECONDS}
          active={!rrg.isFetching}
          updatedAt={rrg.dataUpdatedAt}
        />
      </AnalysisHead>

      <div className={r.controls}>
        <div className={r.control}>
          <span className={s.label}>Timeframe</span>
          <div className={s.segmented} role="group" aria-label="Timeframe">
            {RRG_INTERVALS.map((entry) => (
              <button
                key={entry.id}
                type="button"
                className={cx(s.segment, entry.id === interval && s.segmentOn)}
                aria-pressed={entry.id === interval}
                onClick={() => setInterval(entry.id)}
              >
                {entry.label}
              </button>
            ))}
          </div>
        </div>

        <div className={r.control}>
          <span className={s.label}>Tail</span>
          <div className={r.stepper}>
            <button
              type="button"
              className={r.step}
              onClick={() => setTail((value) => Math.max(TAIL_MIN, value - 1))}
              disabled={tail <= TAIL_MIN}
              aria-label="Shorter tail"
            >
              −
            </button>
            <span className={r.stepValue}>{tail}</span>
            <button
              type="button"
              className={r.step}
              onClick={() => setTail((value) => Math.min(TAIL_MAX, value + 1))}
              disabled={tail >= TAIL_MAX}
              aria-label="Longer tail"
            >
              +
            </button>
          </div>
          <span className={r.unit}>periods</span>
        </div>

        <label className={r.toggle}>
          <input type="checkbox" checked={labels} onChange={() => setLabels((on) => !on)} />
          Labels
        </label>

        {data ? (
          <p className={r.meta}>
            {data.periods} periods · {data.window}-period window · {data.sessions.length} sessions
          </p>
        ) : null}
      </div>

      {rrg.isError ? (
        <p className={s.error}>The rotation graph could not be loaded.</p>
      ) : data === undefined ? (
        <p className={s.placeholder}>Reading the archive…</p>
      ) : filling ? (
        <p className={s.placeholder}>
          The archive is still filling. This board needs {data.periods_required} periods to measure
          a {data.window}-period window twice — once for strength and once for its momentum — and
          has {data.periods}. {intervalAdvice(interval)}
        </p>
      ) : tails.length === 0 ? (
        <p className={s.placeholder}>
          No sector could be priced across the window, so there is nothing to rotate.
        </p>
      ) : (
        <>
          <section className={r.board}>
            <aside className={r.rail}>
              <div className={r.railHead}>
                <span className={s.label}>Sectors</span>
                <span className={r.railCount}>
                  {shown.length}/{tails.length}
                </span>
              </div>
              <ul className={r.list}>
                {tails.map((entry) => (
                  <li key={entry.sector}>
                    <label
                      className={cx(
                        r.row,
                        QUADRANT_CLASS[entry.quadrant],
                        hidden.has(entry.sector) && r.rowOff
                      )}
                    >
                      <input
                        type="checkbox"
                        checked={!hidden.has(entry.sector)}
                        onChange={() => toggle(entry.sector)}
                      />
                      <span className={r.rowName}>{entry.sector}</span>
                      <span className={cx(r.rowValue, 'cn-numeric')}>{head(entry, 'x')}</span>
                      <span className={cx(r.rowValue, 'cn-numeric')}>{head(entry, 'y')}</span>
                    </label>
                  </li>
                ))}
              </ul>
            </aside>

            <div className={r.plot}>
              <EChart
                option={option}
                className={r.chart}
                resetKey={`${index}-${interval}-${tail}`}
              />
            </div>
          </section>

          <div className={r.legend}>
            {QUADRANTS.map((quadrant) => (
              <span key={quadrant.id} className={cx(r.chip, QUADRANT_CLASS[quadrant.id])}>
                {quadrant.label}
                <strong>{tails.filter((t) => t.quadrant === quadrant.id).length}</strong>
              </span>
            ))}
          </div>

          <section className={s.card}>
            <div className={s.cardHead}>
              <h2 className={s.cardTitle}>Where each sector stands</h2>
              <p className={s.cardNote}>Strongest first</p>
            </div>
            <div className={s.tableWrap}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th scope="col">Sector</th>
                    <th scope="col">RS-Ratio</th>
                    <th scope="col">RS-Momentum</th>
                    <th scope="col">Quadrant</th>
                    <th scope="col">Measured</th>
                  </tr>
                </thead>
                <tbody>
                  {[...tails]
                    .sort((a, b) => axis(b, 'x') - axis(a, 'x'))
                    .map((entry) => (
                      <tr key={entry.sector}>
                        <td className={s.symbol}>{entry.sector}</td>
                        <td className={cx(tone(axis(entry, 'x')))}>{head(entry, 'x')}</td>
                        <td className={cx(tone(axis(entry, 'y')))}>{head(entry, 'y')}</td>
                        <td>{quadrantMeta(entry.quadrant).label}</td>
                        <td>
                          {entry.measured} / {entry.members}
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>
          </section>

          <p className={s.note}>
            Both axes are z-scores centred on 100, not index points: a sector at 101.5 is one and a
            half standard deviations above its own recent relative strength, which is what lets
            sectors of very different sizes share one grid. Sectors have no published index, so each
            one&rsquo;s level is an equal-weighted composite of its members, rebased across the
            window — the <em>Measured</em> column says how many of them priced.
          </p>
        </>
      )}
    </div>
  );
}

/** The head point's coordinate, or 100 (dead centre) when a tail is empty. */
function axis(entry: RrgTail, which: 'x' | 'y'): number {
  const point = entry.points.at(-1);
  if (!point) return 100;
  return which === 'x' ? point.rs_ratio : point.rs_momentum;
}

function head(entry: RrgTail, which: 'x' | 'y'): string {
  return axis(entry, which).toFixed(2);
}

/** Above the cross is strength, below it is weakness — the table's only tone. */
function tone(value: number): string | undefined {
  if (value === 100) return undefined;
  return value > 100 ? s.up : s.down;
}

function formatStamp(iso: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime())
    ? iso
    : at.toLocaleString('en-IN', {
        day: '2-digit',
        month: 'short',
        hour: '2-digit',
        minute: '2-digit'
      });
}

/** What the reader can actually do about a half-filled window. */
function intervalAdvice(interval: RrgInterval): string {
  return interval === '1d'
    ? 'The daily axis needs about thirteen captured sessions; the 15m and 1h axes reach their window inside two.'
    : 'Leave the capture worker running — an intraday window fills within two sessions.';
}
