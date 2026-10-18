import { useMemo } from 'react';
import EChart from '$shared/charts/EChart';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { cx } from '$shared/ui/cx';
import { atmIv, historicalVolatility, ivSmile } from '../calc/analytics';
import { type EnrichedChain, atmIndex, windowAround } from '../calc/chain';
import { EMPTY, fmtPercent, fmtPrice } from '../calc/format';
import s from '../stock-watch.module.css';

interface Props {
  chain: EnrichedChain;
  /** Daily closes, newest last — for realised volatility. */
  dailyCloses: number[];
  /** How many daily bars the series actually had, for the honesty note. */
  dailyBars: number;
}

/**
 * Implied volatility across the ladder, and what it is worth next to realised.
 *
 * **IV rank and IV percentile are deliberately absent.** Both need a long
 * history of this stock's own at-the-money implied volatility, and this
 * application archives that for indices only — `/options/iv-history` has no
 * single-stock series. Showing a percentile computed over a handful of
 * intraday readings would be arithmetic wearing a statistic's clothes, and a
 * trader sizing a premium-selling trade off "IV is in the 90th percentile"
 * when the sample is nine observations is being actively misled. The panel
 * says what is missing instead.
 */
export default function VolatilityPanel({ chain, dailyCloses, dailyBars }: Props) {
  const theme = useChartTheme();

  const smile = useMemo(() => {
    const centre = atmIndex(chain.rows, chain.spot, chain.atmStrike);
    return ivSmile(windowAround(chain.rows, centre, 12));
  }, [chain]);

  const atm = useMemo(() => atmIv(chain), [chain]);
  const hv = useMemo(() => historicalVolatility(dailyCloses), [dailyCloses]);
  const spread = atm != null && hv != null ? atm - hv : undefined;

  const option = useMemo(() => {
    const strikes = smile.map((point) => String(point.strike));
    return {
      backgroundColor: 'transparent',
      grid: { left: 8, right: 16, top: 28, bottom: 8, containLabel: true },
      tooltip: {
        trigger: 'axis',
        appendTo: 'body',
        backgroundColor: theme.tooltipBg,
        borderColor: theme.grid,
        textStyle: { color: theme.tooltipText, fontSize: 12 }
      },
      legend: { top: 0, textStyle: { color: theme.axis, fontSize: 11 } },
      xAxis: {
        type: 'category',
        data: strikes,
        axisLine: { lineStyle: { color: theme.grid } },
        axisTick: { show: false },
        axisLabel: { color: theme.axis, fontSize: 11 }
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: {
          color: theme.axis,
          fontSize: 11,
          formatter: (v: number) => `${v.toFixed(0)}%`
        },
        splitLine: { lineStyle: { color: theme.grid } }
      },
      series: [
        {
          name: 'Call IV',
          type: 'line',
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 2, color: '#f2495c' },
          itemStyle: { color: '#f2495c' },
          // `null`, not 0: an unquoted strike must leave a gap in the curve
          // rather than drag it to the axis and invent a volatility smile.
          data: smile.map((point) => point.callIv ?? null)
        },
        {
          name: 'Put IV',
          type: 'line',
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 2, color: '#17b877' },
          itemStyle: { color: '#17b877' },
          data: smile.map((point) => point.putIv ?? null)
        }
      ]
    };
  }, [smile, theme]);

  return (
    <div className={s.stack}>
      <section className={s.panel}>
        <div className={s.panelHead}>
          <div>
            <h2 className={s.panelTitle}>Volatility</h2>
            <p className={s.panelSub}>
              {chain.expiry} · {chain.daysToExpiry} days to expiry
            </p>
          </div>
        </div>
        <div className={s.panelBody}>
          <dl className={s.readout} style={{ borderTop: 0, paddingTop: 0 }}>
            <div>
              <dt className={s.readoutKey}>ATM implied</dt>
              <dd className={cx(s.readoutValue, 'cn-numeric')}>
                {atm != null ? `${atm.toFixed(2)}%` : EMPTY}
              </dd>
            </div>
            <div>
              <dt className={s.readoutKey}>Realised (daily, annualised)</dt>
              <dd className={cx(s.readoutValue, 'cn-numeric')}>
                {hv != null ? `${hv.toFixed(2)}%` : EMPTY}
              </dd>
            </div>
            <div>
              <dt className={s.readoutKey}>Implied − realised</dt>
              <dd
                className={cx(
                  s.readoutValue,
                  spread != null ? (spread > 0 ? s.warn : s.up) : undefined,
                  'cn-numeric'
                )}
              >
                {spread != null ? fmtPercent(spread) : EMPTY}
              </dd>
            </div>
            <div>
              <dt className={s.readoutKey}>IV percentile / rank</dt>
              <dd className={cx(s.readoutValue, s.muted)}>Not available</dd>
            </div>
          </dl>

          {hv == null ? (
            <p className={cx(s.notice, s.noticeWarn)} style={{ marginTop: 'var(--cn-space-3)' }}>
              <span>
                Realised volatility needs at least 21 daily closes; this series has {dailyBars}. The
                standard deviation of a handful of returns is not a volatility, so none is shown.
              </span>
            </p>
          ) : null}

          <p className={s.notice} style={{ marginTop: 'var(--cn-space-2)' }}>
            <span>
              <strong>No IV percentile or IV rank.</strong> Both require a long history of this
              stock&apos;s own at-the-money implied volatility, and this application archives that
              for indices only. A percentile over a few readings would look like a statistic and
              behave like noise, so the field stays empty until a single-stock IV archive exists.
            </span>
          </p>
        </div>
      </section>

      <section className={s.panel}>
        <div className={s.panelHead}>
          <div>
            <h2 className={s.panelTitle}>IV smile and skew</h2>
            <p className={s.panelSub}>Per-strike implied volatility, as the chain quotes it</p>
          </div>
        </div>
        <div className={s.panelBody}>
          {smile.length === 0 ? (
            <p className={s.empty}>This chain carries no implied volatility.</p>
          ) : (
            <EChart
              option={option}
              resetKey={`${chain.expiry}:smile`}
              className={s.chartBox}
              style={{ height: '16rem' }}
            />
          )}
        </div>
      </section>

      <section className={s.panel}>
        <div className={s.panelHead}>
          <div>
            <h2 className={s.panelTitle}>Greeks near the money</h2>
            <p className={s.panelSub}>
              Black-Scholes, computed here — 7% rate, no dividend, European exercise
            </p>
          </div>
        </div>
        <div className={s.panelBodyFlush}>
          <GreeksTable chain={chain} />
          <p className={s.notice} style={{ margin: 'var(--cn-space-3)' }}>
            <span>
              <strong>What these risks actually do to a long option.</strong> Theta is the premium
              the clock takes every calendar day, and it takes it whether or not the underlying
              moves. A fall in implied volatility can cut the premium even when the stock goes the
              way you wanted — the most common way a correct directional call still loses money.
              Gamma makes delta change quickly near the strike and near expiry, so a position that
              was comfortably hedged this morning may not be this afternoon. Vega is sensitivity to
              volatility, not a forecast of it. And delta is a hedge ratio: a 0.30 delta is not a
              30% chance of profit.
            </span>
          </p>
        </div>
      </section>
    </div>
  );
}

function GreeksTable({ chain }: { chain: EnrichedChain }) {
  const rows = useMemo(() => {
    const centre = atmIndex(chain.rows, chain.spot, chain.atmStrike);
    return windowAround(chain.rows, centre, 5);
  }, [chain]);

  if (rows.length === 0) return <p className={s.empty}>No strikes near the money.</p>;

  return (
    <div className={s.tableScroll}>
      <table className={s.table}>
        <thead>
          <tr>
            <th colSpan={5} className={s.left}>
              Call (model)
            </th>
            <th>Strike</th>
            <th colSpan={5} className={s.left}>
              Put (model)
            </th>
          </tr>
          <tr>
            <th>δ</th>
            <th>γ</th>
            <th>θ/day</th>
            <th>ν/pt</th>
            <th>IV</th>
            <th />
            <th>IV</th>
            <th>ν/pt</th>
            <th>θ/day</th>
            <th>γ</th>
            <th>δ</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.strike} className={cx(row.atm && s.rowAtm)}>
              <td>{row.ce?.modelGreeks ? row.ce.modelGreeks.delta.toFixed(3) : EMPTY}</td>
              <td>{row.ce?.modelGreeks ? row.ce.modelGreeks.gamma.toFixed(5) : EMPTY}</td>
              <td className={s.down}>
                {row.ce?.modelGreeks ? row.ce.modelGreeks.theta.toFixed(2) : EMPTY}
              </td>
              <td>{row.ce?.modelGreeks ? row.ce.modelGreeks.vega.toFixed(3) : EMPTY}</td>
              <td>{row.ce?.iv != null ? `${row.ce.iv.toFixed(1)}%` : EMPTY}</td>
              <td className={s.strikeCell}>{fmtPrice(row.strike)}</td>
              <td>{row.pe?.iv != null ? `${row.pe.iv.toFixed(1)}%` : EMPTY}</td>
              <td>{row.pe?.modelGreeks ? row.pe.modelGreeks.vega.toFixed(3) : EMPTY}</td>
              <td className={s.down}>
                {row.pe?.modelGreeks ? row.pe.modelGreeks.theta.toFixed(2) : EMPTY}
              </td>
              <td>{row.pe?.modelGreeks ? row.pe.modelGreeks.gamma.toFixed(5) : EMPTY}</td>
              <td>{row.pe?.modelGreeks ? row.pe.modelGreeks.delta.toFixed(3) : EMPTY}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
