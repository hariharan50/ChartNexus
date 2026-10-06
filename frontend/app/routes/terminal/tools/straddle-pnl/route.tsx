import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { getInstruments } from '$contexts/instrument-catalog/api';
import EChart from '$shared/charts/EChart';
import { buildMultiSeriesOption, type SeriesLine } from '$shared/charts/options/multi-series';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import Select from '$shared/ui/Select';
import SeriesToggle from '$shared/ui/SeriesToggle';
import ExpiryPicker from '../../options/components/ExpiryPicker';
import {
  bucketIndices,
  coverageNote,
  DEFAULT_RANGE,
  DEFAULT_TIMEFRAME,
  exchangeOf,
  formatMoney,
  formatPremium,
  formatPrice,
  formatStrike,
  getStraddlePnl,
  OI_INSTRUMENTS,
  pick,
  PNL,
  PNL_NEGATIVE,
  PNL_POSITIVE,
  RANGES,
  sessionsOf,
  signOf,
  SPOT,
  SPOT_COLOR,
  strikeLabel,
  SYNTHETIC,
  SYNTHETIC_COLOR,
  TIMEFRAMES,
  tradeTime,
  type RunParams,
  type StraddlePnlView,
  type Timeframe
} from './pnl-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Straddle PnL Simulator · Tools' }];

/**
 * Straddle PnL Simulator — the adjusted short straddle, replayed.
 *
 * Sells the at-the-money call and put at each session's first capture,
 * re-strikes whenever the at-the-money has travelled `Adj Points` away from the
 * strike held, and squares off at the close. The curve is the running P&L; the
 * trade log is every leg it took to get there.
 *
 * **The run is explicit.** Every other tool here polls, because every other tool
 * answers "what is happening now". This one answers "what would have happened",
 * which does not change until a parameter does — so it runs when asked and the
 * stats strip blanks the moment a control moves away from the run on screen.
 * The chart stays until the next run rather than flashing empty, which is what
 * makes comparing two settings possible.
 */
export default function StraddlePnlSimulator() {
  const [instIdx, setInstIdx] = useState(0);
  const [expiry, setExpiry] = useState<string | undefined>(undefined);
  const [timeframe, setTimeframe] = useState<Timeframe>(DEFAULT_TIMEFRAME);
  const [range, setRange] = useState(DEFAULT_RANGE);
  // `null` means "whatever the contract says" — the catalog fills the box, and
  // typing replaces it until the instrument changes.
  const [lotOverride, setLotOverride] = useState<string | null>(null);
  const [adjOverride, setAdjOverride] = useState<string | null>(null);
  const [lots, setLots] = useState('1');
  const [showSpot, setShowSpot] = useState(false);
  const [showSynthetic, setShowSynthetic] = useState(false);
  const [run, setRun] = useState<RunParams | null>(null);
  const [zoomNonce, setZoomNonce] = useState(0);

  const theme = useChartTheme();
  const instrument = OI_INSTRUMENTS[instIdx] ?? OI_INSTRUMENTS[0]!;

  // The contract's own size and ladder, which seed the two number boxes. One
  // unpaged call for ~3 index rows, cached for the session.
  const catalog = useQuery({
    queryKey: ['instruments', 'index'],
    queryFn: () => getInstruments({ kind: 'index' }),
    staleTime: 60 * 60 * 1000
  });
  const entry = catalog.data?.instruments.find((row) => row.symbol === instrument.symbol);

  const lotSize = lotOverride ?? (entry ? String(entry.lot_size) : '');
  const adjPoints = adjOverride ?? (entry?.strike_step ? String(Number(entry.strike_step)) : '');
  const quantity = (Number(lotSize) || 0) * (Number(lots) || 0);

  const draft: RunParams | null =
    Number(lotSize) > 0 && Number(lots) > 0 && Number(adjPoints) > 0
      ? {
          instrument: instrument.symbol,
          expiry,
          sessions: sessionsOf(range),
          adjustmentPoints: Number(adjPoints),
          lotSize: Number(lotSize),
          lots: Number(lots)
        }
      : null;

  const query = useQuery<StraddlePnlView>({
    queryKey: ['tools', 'straddle-pnl', run],
    queryFn: () => getStraddlePnl(run!),
    enabled: run !== null,
    // A replay of archived sessions does not change under us; re-running is the
    // reader's decision, not a timer's.
    refetchOnWindowFocus: false,
    staleTime: Infinity
  });

  const view = query.data;
  // The strip describes the run on screen. The moment a control disagrees with
  // it, the numbers belong to settings nobody is looking at any more.
  const stale = run === null || draft === null || !sameRun(run, draft);
  const stats = stale || !view || view.series.length === 0 ? null : view;

  /** The plotted rows, bucketed to the chosen interval. */
  const plot = useMemo(() => {
    if (!view || view.series.length === 0) return null;
    const stamps = view.series.map((point) => point.t);
    const keep = bucketIndices(stamps, timeframe);
    return {
      rows: pick(view.series, keep),
      timestamps: pick(stamps, keep)
    };
  }, [view, timeframe]);

  const option = useMemo(() => {
    if (!plot) return null;

    const priceLines: SeriesLine[] = [];
    if (showSpot) {
      priceLines.push({
        id: 'spot',
        label: SPOT,
        color: SPOT_COLOR,
        values: plot.rows.map((row) => row.spot)
      });
    }
    if (showSynthetic) {
      priceLines.push({
        id: 'synthetic',
        label: SYNTHETIC,
        color: SYNTHETIC_COLOR,
        values: plot.rows.map((row) => row.synthetic_future),
        // Dotted: it tracks spot within a few points all day, and solid the two
        // read as one thick line — losing the gap, which is the information.
        dashed: true
      });
    }

    const built = buildMultiSeriesOption(
      {
        timestamps: plot.timestamps,
        futures: plot.rows.map((row) => row.spot),
        showFutures: false,
        priceLines,
        priceAxisName: 'Index',
        // Nothing is drawn against the left axis while both its lines are off,
        // and an axis that measures nothing still prints a ladder of numbers.
        hidePriceAxis: priceLines.length === 0,
        lines: [
          {
            id: 'pnl',
            label: PNL,
            color: PNL_POSITIVE,
            values: plot.rows.map((row) => row.pnl),
            fill: true,
            // Band closes to zero, and the colour turns on the same line.
            fillOrigin: 0,
            signed: { positive: PNL_POSITIVE, negative: PNL_NEGATIVE }
          }
        ],
        formatValue: formatMoney,
        formatPrice,
        valueAxisName: 'P&L',
        zoomable: true
      },
      theme
    );

    // The shared tooltip lists the plotted lines, which here is one. The reading
    // a replay needs is the whole position at that instant — which strike it was
    // holding versus where the money had moved to — and those are not series.
    return {
      ...built,
      tooltip: {
        ...(built.tooltip as Record<string, unknown>),
        formatter: (params: unknown) => {
          const first = (Array.isArray(params) ? params[0] : params) as
            { dataIndex?: number } | undefined;
          const row = plot.rows[first?.dataIndex ?? -1];
          return row ? tooltipHtml(row, theme.tooltipText) : '';
        }
      }
    };
  }, [plot, theme, showSpot, showSynthetic]);

  const note = stale ? null : coverageNote(view);

  return (
    <div className={s.page}>
      <section className={s.panel}>
        <header className={s.head}>
          <h1 className={s.title}>Straddle PnL Simulator</h1>
        </header>

        {/* -- row 1: the contract ----------------------------------------- */}
        <div className={s.controls}>
          <Select
            className={s.narrow}
            value={exchangeOf(instrument.symbol)}
            ariaLabel="Exchange"
            disabled
            onChange={() => undefined}
            options={[
              { value: exchangeOf(instrument.symbol), label: exchangeOf(instrument.symbol) }
            ]}
          />

          <Select
            className={s.field}
            value={String(instIdx)}
            ariaLabel="Underlying"
            onChange={(next) => {
              setInstIdx(Number(next));
              // All three are per instrument: a NIFTY expiry, lot and ladder
              // mean nothing on SENSEX.
              setExpiry(undefined);
              setLotOverride(null);
              setAdjOverride(null);
            }}
            options={OI_INSTRUMENTS.map((row, index) => ({
              value: String(index),
              label: row.short
            }))}
          />

          <ExpiryPicker
            instrument={instrument.symbol}
            value={expiry}
            onChange={setExpiry}
            resolved={view?.expiry_date}
            archiveBound
            dataQuality={view?.data_quality}
            hideLabel
            className={s.expiry}
          />

          <Select
            className={s.narrow}
            value={timeframe}
            ariaLabel="Interval"
            onChange={setTimeframe}
            options={TIMEFRAMES.map((row) => ({ value: row.value, label: row.label }))}
          />

          <Select
            className={s.days}
            value={range}
            ariaLabel="Days"
            onChange={setRange}
            options={RANGES.map((row) => ({
              value: row.value,
              label: row.label,
              hint: row.sessions === 1 ? 'Today' : 'Sessions'
            }))}
          />
        </div>

        {/* -- row 2: the position ----------------------------------------- */}
        <div className={s.controls}>
          <label className={s.numField}>
            <span className={s.numLabel}>Lot Size</span>
            <input
              className={s.num}
              type="number"
              min={1}
              value={lotSize}
              onChange={(event) => setLotOverride(event.target.value)}
            />
          </label>

          <label className={s.numField}>
            <span className={s.numLabel}>Lots</span>
            <input
              className={s.numSm}
              type="number"
              min={1}
              value={lots}
              onChange={(event) => setLots(event.target.value)}
            />
          </label>

          <label className={s.numField}>
            <span className={s.numLabel}>Adj Points</span>
            <input
              className={s.num}
              type="number"
              min={1}
              value={adjPoints}
              onChange={(event) => setAdjOverride(event.target.value)}
            />
          </label>

          <span className={s.qty}>
            Qty: <b className="cn-numeric">{quantity > 0 ? quantity : '—'}</b>
          </span>

          <button
            type="button"
            className={s.simulate}
            disabled={draft === null || query.isFetching}
            onClick={() => draft && setRun(draft)}
          >
            {query.isFetching ? 'Simulating…' : 'Simulate'}
          </button>
        </div>

        {/* -- the headline figures ---------------------------------------- */}
        {stats ? (
          <div className={s.stats}>
            <span className={s.stat}>
              <span className={s.statLabel}>P&amp;L</span>
              <b className={`cn-numeric ${s[signOf(stats.summary.total_pnl)]}`}>
                {formatMoney(stats.summary.total_pnl)}
              </b>
            </span>
            <span className={s.stat}>
              <span className={s.statLabel}>Adjustments</span>
              <b className="cn-numeric">{stats.summary.total_adjustments}</b>
            </span>
            <span className={s.stat}>
              <span className={s.statLabel}>Max</span>
              <b className={`cn-numeric ${s.pos}`}>{formatMoney(stats.summary.max_pnl)}</b>
            </span>
            <span className={s.stat}>
              <span className={s.statLabel}>Min</span>
              <b className={`cn-numeric ${s.neg}`}>{formatMoney(stats.summary.min_pnl)}</b>
            </span>
            <span className={s.stat}>
              <span className={s.statLabel}>Spot</span>
              <b className="cn-numeric">{stats.spot == null ? '—' : formatPrice(stats.spot)}</b>
            </span>
            <span className={s.stat}>
              <span className={s.statLabel}>Entry Strike</span>
              <b className="cn-numeric">
                {stats.entry_strike == null ? '—' : formatStrike(stats.entry_strike)}
              </b>
            </span>
          </div>
        ) : null}

        {query.isError ? (
          <div className={s.panelError} role="alert">
            <p>Couldn’t run the simulation for this contract.</p>
            <button type="button" onClick={() => void query.refetch()}>
              Retry
            </button>
          </div>
        ) : (
          <>
            {option ? (
              <EChart
                option={option}
                resetKey={`${instrument.symbol}-${timeframe}-${range}-${zoomNonce}`}
                className={s.chart}
              />
            ) : (
              <p className={s.empty}>
                {query.isFetching
                  ? 'Running simulation…'
                  : run === null
                    ? 'Choose a contract and press Simulate.'
                    : 'No captures to replay for this window.'}
              </p>
            )}

            <div className={s.legend}>
              <SeriesToggle
                label={PNL}
                color={PNL_POSITIVE}
                on
                onToggle={() => undefined}
                disabledReason="The P&L curve is the chart; it cannot be switched off"
              />
              <SeriesToggle
                label={SPOT}
                color={SPOT_COLOR}
                on={showSpot}
                onToggle={() => setShowSpot((on) => !on)}
              />
              <SeriesToggle
                label={SYNTHETIC}
                dashed
                on={showSynthetic}
                onToggle={() => setShowSynthetic((on) => !on)}
              />
              <span className={s.spacer} />
              <button
                type="button"
                className={s.zoomReset}
                onClick={() => setZoomNonce((n) => n + 1)}
                title="Back to the whole window"
              >
                ⤢ Reset zoom
              </button>
            </div>
          </>
        )}

        {note ? <p className={s.quality}>{note}</p> : null}
        <p className={s.disclaimer}>
          Gross P&amp;L on captured prices — no brokerage, slippage, taxes or margin, and no
          assumption that either leg could be filled at the price shown. The position is short one
          at-the-money call and put, re-struck whenever the at-the-money strike has moved “Adj
          Points” from the one held, and squared off at each session’s close. For educational and
          informational purposes only.
        </p>
      </section>

      {/* -- the trade log ------------------------------------------------- */}
      {view && view.trades.length > 0 && !stale ? (
        <section className={s.panel}>
          <h2 className={s.subtitle}>Trade Log ({view.trades.length} trades)</h2>
          <div className={s.tableWrap}>
            <table className={s.table}>
              <thead>
                <tr>
                  <th scope="col">Time</th>
                  <th scope="col">Type</th>
                  <th scope="col" className={s.right}>
                    Strike
                  </th>
                  <th scope="col" className={s.right}>
                    CE
                  </th>
                  <th scope="col" className={s.right}>
                    PE
                  </th>
                  <th scope="col" className={s.right}>
                    Straddle
                  </th>
                  <th scope="col" className={s.right}>
                    Spot
                  </th>
                  <th scope="col" className={s.right}>
                    Leg P&amp;L
                  </th>
                  <th scope="col" className={s.right}>
                    Cumulative
                  </th>
                </tr>
              </thead>
              <tbody>
                {view.trades.map((trade, index) => (
                  <tr key={`${trade.t}-${trade.type}-${index}`}>
                    <td className={s.when}>{tradeTime(trade.t)}</td>
                    <td className={s[trade.type.toLowerCase()]}>{trade.type}</td>
                    <td className={`${s.right} cn-numeric`}>{strikeLabel(trade)}</td>
                    <td className={`${s.right} cn-numeric`}>{formatPremium(trade.ce_price)}</td>
                    <td className={`${s.right} cn-numeric`}>{formatPremium(trade.pe_price)}</td>
                    <td className={`${s.right} cn-numeric`}>{formatPremium(trade.straddle)}</td>
                    <td className={`${s.right} cn-numeric`}>{formatPrice(trade.spot)}</td>
                    <td className={`${s.right} cn-numeric ${s[signOf(trade.leg_pnl)]}`}>
                      {trade.leg_pnl == null ? '–' : formatMoney(trade.leg_pnl)}
                    </td>
                    <td className={`${s.right} cn-numeric ${s[signOf(trade.cumulative_pnl)]}`}>
                      {formatMoney(trade.cumulative_pnl)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </div>
  );
}

/** Two runs are the same run when every parameter that feeds the replay matches. */
function sameRun(a: RunParams, b: RunParams): boolean {
  return (
    a.instrument === b.instrument &&
    a.expiry === b.expiry &&
    a.sessions === b.sessions &&
    a.adjustmentPoints === b.adjustmentPoints &&
    a.lotSize === b.lotSize &&
    a.lots === b.lots
  );
}

/** The crosshair readout: the whole position at one capture. */
function tooltipHtml(
  row: {
    t: string;
    spot: number;
    atm_strike: number;
    entry_strike: number;
    straddle: number;
    synthetic_future: number;
    pnl: number;
    adjustments: number;
  },
  textColor: string
): string {
  const line = (label: string, value: string, color?: string) =>
    `<div style="display:flex;gap:16px;justify-content:space-between;line-height:1.6">` +
    `<span style="opacity:.75">${label}</span>` +
    `<span style="font-weight:700${color ? `;color:${color}` : ''}">${value}</span>` +
    `</div>`;

  return (
    `<div style="font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;color:${textColor}">` +
    line('P&L', formatMoney(row.pnl), row.pnl >= 0 ? PNL_POSITIVE : PNL_NEGATIVE) +
    line('Spot', formatPrice(row.spot)) +
    line('ATM Strike', formatStrike(row.atm_strike)) +
    line('Entry Strike', formatStrike(row.entry_strike)) +
    line('Straddle', formatPremium(row.straddle)) +
    line('Synthetic Fut', formatPrice(row.synthetic_future), SYNTHETIC_COLOR) +
    line('Adjustments', String(row.adjustments)) +
    `<div style="margin-top:6px;padding-top:6px;border-top:1px solid currentColor;opacity:.6">` +
    tradeTime(row.t) +
    `</div></div>`
  );
}
