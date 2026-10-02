import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
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
  formatPremium,
  formatPrice,
  formatStrike,
  getStraddleChart,
  OI_INSTRUMENTS,
  pick,
  RANGES,
  REFETCH_MS,
  sessionsOf,
  SPOT,
  STRADDLE,
  straddleColors,
  SYNTHETIC,
  TIMEFRAMES,
  type StraddleChartView,
  type Timeframe
} from './straddle-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Straddle Chart · Tools' }];

/**
 * Straddle Chart — what it costs to be at the money, through the session.
 *
 * The strike rolls: every point is priced at its own at-the-money strike, so
 * the line is "the cost of being at the money" rather than one contract's
 * price. The header names the strike in force now; the tooltip names the one
 * each point belonged to, because those differ as soon as the index moves.
 *
 * Built on the same chart as MultiStrike and Multi OI & Volume — the trading-
 * minutes axis, wheel-to-zoom, drag-to-pan, end-of-line value pills, and legend
 * chips that switch a series off. The premium is the one line on the right
 * axis; spot and the synthetic forward are index levels and sit on the left
 * price axis with the same scale as each other.
 */
export default function StraddleChart() {
  const [instIdx, setInstIdx] = useState(0);
  const [expiry, setExpiry] = useState<string | undefined>(undefined);
  const [timeframe, setTimeframe] = useState<Timeframe>(DEFAULT_TIMEFRAME);
  const [range, setRange] = useState(DEFAULT_RANGE);
  const [showSpot, setShowSpot] = useState(false);
  const [showSynthetic, setShowSynthetic] = useState(false);
  // Bumped by Reset zoom: it feeds `resetKey`, and a rebuild is what re-applies
  // the chart's default window. Same mechanism as MultiStrike.
  const [zoomNonce, setZoomNonce] = useState(0);

  const theme = useChartTheme();
  const colors = straddleColors(theme);
  const instrument = OI_INSTRUMENTS[instIdx] ?? OI_INSTRUMENTS[0]!;
  const sessions = sessionsOf(range);

  const query = useQuery<StraddleChartView>({
    queryKey: ['tools', 'straddle-chart', instrument.symbol, expiry, sessions],
    queryFn: () => getStraddleChart(instrument.symbol, { expiry, sessions }),
    refetchInterval: REFETCH_MS
  });

  const view = query.data;

  /** The plotted arrays, bucketed to the chosen interval. */
  const plot = useMemo(() => {
    if (!view || view.series.t.length === 0) return null;
    const keep = bucketIndices(view.series.t, timeframe);
    const series = view.series;
    return {
      timestamps: pick(series.t, keep),
      strikes: pick(series.strike, keep),
      straddle: pick<number | null>(series.straddle, keep),
      spot: pick(series.spot, keep),
      synthetic: pick(series.synthetic, keep)
    };
  }, [view, timeframe]);

  const option = useMemo(() => {
    if (!plot) return null;

    const priceLines: SeriesLine[] = [];
    if (showSynthetic) {
      priceLines.push({
        id: 'synthetic',
        label: SYNTHETIC,
        color: colors[SYNTHETIC]!,
        values: plot.synthetic,
        // Dotted: it tracks spot within a few points all day, and solid the two
        // read as one thick line — losing the gap, which is the information.
        dashed: true
      });
    }

    return buildMultiSeriesOption(
      {
        timestamps: plot.timestamps,
        // Spot is the price reference this chart reads against, so it takes the
        // slot the Options Lab charts give the future.
        futures: plot.spot,
        showFutures: showSpot,
        priceLines,
        priceAxisName: 'Spot',
        lines: [
          {
            id: 'straddle',
            label: STRADDLE,
            color: colors[STRADDLE]!,
            values: plot.straddle,
            // One subject line, so it reads better as a filled band.
            fill: true
          }
        ],
        formatValue: formatPremium,
        formatPrice,
        valueAxisName: 'Straddle',
        zoomable: true
      },
      theme
    );
  }, [plot, theme, colors, showSpot, showSynthetic]);

  const note = coverageNote(view);
  const strike = view?.atm_strike == null ? null : formatStrike(view.atm_strike);

  return (
    <div className={s.page}>
      <header className={s.head}>
        <h1 className={s.title}>Straddle Chart</h1>
      </header>

      {/* -- controls ------------------------------------------------------ */}
      <div className={s.controls}>
        {/* One option, and not a placeholder: the chain this page reads is
            NFO's. Shown so the row names the instrument's full address. */}
        <Select
          className={s.field}
          value="NFO"
          ariaLabel="Exchange"
          disabled
          onChange={() => undefined}
          options={[{ value: 'NFO', label: 'NFO' }]}
        />

        <Select
          className={s.field}
          value={String(instIdx)}
          ariaLabel="Symbol"
          onChange={(next) => {
            setInstIdx(Number(next));
            // Expiries are per instrument; a NIFTY date means nothing on SENSEX.
            setExpiry(undefined);
          }}
          options={OI_INSTRUMENTS.map((entry, index) => ({
            value: String(index),
            label: entry.short
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
          className={s.field}
          value={timeframe}
          ariaLabel="Interval"
          onChange={setTimeframe}
          options={TIMEFRAMES.map((entry) => ({ value: entry.value, label: entry.label }))}
        />

        <Select
          className={s.field}
          value={range}
          ariaLabel="Range"
          onChange={setRange}
          options={RANGES.map((entry) => ({
            value: entry.value,
            label: entry.label,
            hint: entry.sessions === 1 ? 'Today' : 'Sessions'
          }))}
        />

        <button
          type="button"
          className={s.refresh}
          onClick={() => void query.refetch()}
          disabled={query.isFetching}
        >
          {query.isFetching ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {/* -- where the right edge is sitting ------------------------------- */}
      <div className={s.context}>
        <span className={s.ctxItem}>
          <span className={s.ctxLabel}>Straddle Price</span>
          <b className="mc-numeric">
            {view?.straddle_price == null ? '—' : formatPremium(view.straddle_price)}
          </b>
        </span>
        <span className={s.ctxItem}>
          <span className={s.ctxLabel}>Spot</span>
          <b className="mc-numeric">{view?.spot == null ? '—' : formatPrice(view.spot)}</b>
        </span>
        <span className={s.ctxItem}>
          <span className={s.ctxLabel}>Straddle Strike</span>
          <b className="mc-numeric">{strike ?? '—'}</b>
        </span>
        <span className={s.ctxItem}>
          <span className={s.ctxLabel}>{strike ? `${strike} CE` : 'CE'}</span>
          <b className="mc-numeric">{view?.ce_ltp == null ? '—' : formatPremium(view.ce_ltp)}</b>
        </span>
        <span className={s.ctxItem}>
          <span className={s.ctxLabel}>{strike ? `${strike} PE` : 'PE'}</span>
          <b className="mc-numeric">{view?.pe_ltp == null ? '—' : formatPremium(view.pe_ltp)}</b>
        </span>
      </div>

      {query.isError ? (
        <div className={s.panelError} role="alert">
          <p>Couldn’t load the straddle for this contract.</p>
          <button type="button" onClick={() => void query.refetch()}>
            Retry
          </button>
        </div>
      ) : (
        <section className={s.panel}>
          {/* Chips above the plot, as on MultiStrike. Spot and the forward start
              switched off: they answer "was that the index, or volatility?",
              which is a question a reader asks after looking at the premium. */}
          <div className={s.legend}>
            <SeriesToggle
              label={STRADDLE}
              color={colors[STRADDLE]}
              on
              onToggle={() => undefined}
              disabledReason="The straddle is the chart; it cannot be switched off"
            />
            <SeriesToggle
              label={SPOT}
              dashed
              on={showSpot}
              onToggle={() => setShowSpot((on) => !on)}
            />
            <SeriesToggle
              label={SYNTHETIC}
              color={colors[SYNTHETIC]}
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

          {option ? (
            <EChart
              option={option}
              resetKey={`${instrument.symbol}-${timeframe}-${range}-${zoomNonce}`}
              className={s.chart}
            />
          ) : (
            <p className={s.empty}>
              {query.isPending ? 'Loading…' : 'No captures to draw for this window.'}
            </p>
          )}
        </section>
      )}

      {note ? <p className={s.quality}>{note}</p> : null}
      <p className={s.disclaimer}>
        The strike rolls with the money, so each point is the at-the-money straddle at that moment
        rather than one contract through the window — the tooltip names the strike each reading was
        priced at. “Synthetic Fut” is the put-call parity forward implied by those two legs, falling
        back to the traded future where parity could not be taken. Scroll over the plot to zoom the
        clock, drag inside it to pan, or drag the time axis itself to stretch and squeeze the
        window. For educational and informational purposes only.
      </p>
    </div>
  );
}
