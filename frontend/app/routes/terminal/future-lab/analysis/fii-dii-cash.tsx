import { useMemo, useState } from 'react';
import { useFiiDiiCashQuery } from '$contexts/market-breadth/queries';
import EChart from '$shared/charts/EChart';
import { buildCashFlowOption, type CashFlowPoint } from '$shared/charts/options/fii-dii-cash';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { cx } from '$shared/ui/cx';
import IconFlow from '$shared/ui/icons/IconFlow';
import { dayLabel, fmtCrore, fmtGross, toNumber } from './analysis-data';
import { AnalysisHead, SessionPicker, SourceBadge } from './components/AnalysisHead';
import s from './analysis.module.css';
import type { Route } from './+types/fii-dii-cash';

export const meta: Route.MetaFunction = () => [
  { title: 'FII/DII Cash Market · Future Lab · MarketCompass' }
];

/** Windows the picker offers, in trading sessions. */
const WINDOWS = [20, 60, 120];

const EMPTY: CashFlowPoint[] = [];

/**
 * Cash-market institutional flow across a window of sessions.
 *
 * Two panels, not one chart with two y-axes. The daily nets and the running
 * total have unrelated scales, and overlaying them would let the choice of
 * scale decide where the cumulative line crosses the bars — a crossing that
 * would mean nothing but would be read as if it did.
 *
 * The cumulative lines restart at the first session in the window, which is
 * the only question a windowed chart can honestly answer. Changing the window
 * therefore changes the lines; the caption says so.
 */
export default function FiiDiiCashMarket() {
  const [sessions, setSessions] = useState(WINDOWS[1]!);
  const theme = useChartTheme();
  const cash = useFiiDiiCashQuery({ sessions });
  const data = cash.data;

  const points = useMemo<CashFlowPoint[]>(
    () =>
      data?.days.map((day) => ({
        label: dayLabel(day.session_date),
        fiiNet: toNumber(day.fii_net) ?? 0,
        diiNet: toNumber(day.dii_net) ?? 0,
        fiiCumulative: toNumber(day.fii_cumulative) ?? 0,
        diiCumulative: toNumber(day.dii_cumulative) ?? 0
      })) ?? EMPTY,
    [data]
  );

  const format = (value: number) => fmtGross(value);
  const daily = useMemo(
    () => buildCashFlowOption(points, theme, { mode: 'daily', format }),
    [points, theme]
  );
  const cumulative = useMemo(
    () => buildCashFlowOption(points, theme, { mode: 'cumulative', format }),
    [points, theme]
  );

  return (
    <div className={s.page}>
      <AnalysisHead
        icon={<IconFlow />}
        title="FII/DII Cash Market"
        subtitle="Daily net equity flow and its running total · ₹ crore"
      >
        <span className={s.label}>Window</span>
        <SessionPicker value={sessions} options={WINDOWS} onChange={setSessions} />
        <SourceBadge source={data?.source} />
      </AnalysisHead>

      {cash.isError ? (
        <p className={s.error}>The cash-market flow could not be loaded.</p>
      ) : data === undefined ? (
        <p className={s.placeholder}>Loading the participant file…</p>
      ) : points.length === 0 ? (
        <p className={s.placeholder}>No sessions published in this window.</p>
      ) : (
        <>
          <div className={s.tiles}>
            <Total label={`FII net · ${points.length} sessions`} value={data.fii_total} />
            <Total label={`DII net · ${points.length} sessions`} value={data.dii_total} />
          </div>

          <section className={s.card}>
            <div className={s.cardHead}>
              <h2 className={s.cardTitle}>Daily net</h2>
              {/* The legend is here rather than inside the chart: it applies to
                  both panels, and two identical ECharts legends stacked down the
                  page would be noise. */}
              <Legend />
            </div>
            <EChart option={daily} className={s.chart} resetKey={`daily:${sessions}`} />
          </section>

          <section className={s.card}>
            <div className={s.cardHead}>
              <h2 className={s.cardTitle}>Cumulative net</h2>
              <p className={s.cardNote}>Running total from the first session in this window</p>
            </div>
            <EChart
              option={cumulative}
              className={s.chartShort}
              resetKey={`cumulative:${sessions}`}
            />
          </section>

          <section className={s.card}>
            <div className={s.cardHead}>
              <h2 className={s.cardTitle}>Sessions</h2>
              <p className={s.cardNote}>Most recent first</p>
            </div>
            <div className={s.tableWrap}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th scope="col">Session</th>
                    <th scope="col">FII buy</th>
                    <th scope="col">FII sell</th>
                    <th scope="col">FII net</th>
                    <th scope="col">DII buy</th>
                    <th scope="col">DII sell</th>
                    <th scope="col">DII net</th>
                  </tr>
                </thead>
                <tbody>
                  {[...data.days].reverse().map((day) => {
                    const fii = toNumber(day.fii_net);
                    const dii = toNumber(day.dii_net);
                    return (
                      <tr key={day.session_date}>
                        <td className={s.symbol}>{dayLabel(day.session_date)}</td>
                        <td>{fmtGross(day.fii_buy)}</td>
                        <td>{fmtGross(day.fii_sell)}</td>
                        <td className={cx(signClass(fii))}>{fmtCrore(day.fii_net)}</td>
                        <td>{fmtGross(day.dii_buy)}</td>
                        <td>{fmtGross(day.dii_sell)}</td>
                        <td className={cx(signClass(dii))}>{fmtCrore(day.dii_net)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          {data.source === 'mock' ? (
            <p className={s.note}>
              These figures are generated, not published — see FII/DII Summary for why. The shapes
              are realistic; the sessions are not real.
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}

function Total({ label, value }: { label: string; value: string | number }) {
  const amount = toNumber(value);
  return (
    <div className={s.tile}>
      <span className={s.tileLabel}>{label}</span>
      <span className={cx(s.tileValue, signClass(amount))}>{fmtCrore(value)}</span>
    </div>
  );
}

function Legend() {
  return (
    <p className={s.meterLegend}>
      <span>
        <span className={s.swatch} style={{ background: 'var(--mc-accent)' }} aria-hidden="true" />
        FII
      </span>
      <span>
        <span className={s.swatch} style={{ background: 'var(--mc-warning)' }} aria-hidden="true" />
        DII
      </span>
    </p>
  );
}

/** Up, down, or neither — `undefined` leaves the cell in the default ink. */
function signClass(value: number | null): string | undefined {
  if (value === null || value === 0) return undefined;
  return value > 0 ? s.up : s.down;
}
