import { useEffect, useRef, useState, type CSSProperties, type RefObject } from 'react';
import { cx } from '$shared/ui/cx';
// `import type`, never a value import. Type-only imports are erased entirely at
// compile time, so this costs nothing at runtime and — critically — does not
// pull the library into the server bundle. See the note on SSR below.
import type { IChartApi, ISeriesApi, SeriesType, UTCTimestamp } from 'lightweight-charts';
import type { ChartTheme } from '../theme/types';
import s from './LwChart.module.css';

/**
 * The app's only TradingView Lightweight Charts mount point.
 *
 * A sibling of `EChart`, with the same contract — sized container rendered on
 * the server, resize handling, disposal on unmount — so the two are swappable
 * at the call site and nobody has to learn a second mounting convention. The
 * resize half differs only in who does it: this library has its own observer
 * under `autoSize`, where ECharts needs one supplied.
 *
 * ECharts stays for everything else. This library exists here for one job:
 * price series. Its candlestick is what it was built around, where ECharts'
 * is a general-purpose chart wearing a candle costume.
 *
 * **The library is imported dynamically, inside the effect.** Effects never run
 * during SSR, so the module is never loaded on the server — which matters,
 * because it touches browser globals at import time. A top-level import
 * anywhere in the app would break the server build, and the failure would look
 * like an unrelated SSR crash. It code-splits out of the initial bundle as a
 * bonus.
 */

export interface Candle {
  /** Seconds since the epoch — the library's `UTCTimestamp`. */
  time: number;
  open: number;
  high: number;
  low: number;
  close: number;
}

export interface VolumeBar {
  time: number;
  value: number;
  /** Coloured by the direction of the bar it belongs to. */
  rising: boolean;
}

export type ChartType = 'candle' | 'line' | 'area';

/** What the parent can ask of a mounted chart. */
export interface LwChartHandle {
  /** A PNG of the chart as drawn, for the toolbar's snapshot button. */
  screenshot(): HTMLCanvasElement;
  fitContent(): void;
}

interface Props {
  candles: Candle[];
  /** Omit for a price-only chart; an empty array draws an empty pane. */
  volume?: VolumeBar[] | undefined;
  theme: ChartTheme;
  type?: ChartType;
  /**
   * The bar under the crosshair, or `null` when the pointer leaves.
   *
   * Drives the OHLC legend. Reported from here rather than derived in the
   * parent because only the chart knows which bar the pointer resolved to.
   */
  onHoverBar?: ((bar: Candle | null) => void) | undefined;
  /** Populated on mount, cleared on dispose. */
  handleRef?: RefObject<LwChartHandle | null> | undefined;
  className?: string | undefined;
  style?: CSSProperties | undefined;
}

/** How much of the chart's height the volume pane takes, when there is one. */
const VOLUME_PANE_FRACTION = 0.22;

/**
 * The exchange's clock, not the reader's and not UTC.
 *
 * The library formats the time scale in UTC unless told otherwise, which put an
 * Indian session — 09:15 to 15:30 IST — on screen as 03:45 to 10:00, and dropped
 * the day-boundary tick at 00:00 UTC, i.e. 05:30 IST, in the middle of the
 * drawn bars. Every reading on the axis was two decimal hours out from the
 * market it described.
 *
 * India observes no DST, so this is a fixed offset and needs no tzdata.
 */
const IST = 'Asia/Kolkata';

const tickClock = new Intl.DateTimeFormat('en-GB', {
  timeZone: IST,
  hour: '2-digit',
  minute: '2-digit',
  hour12: false
});

const tickDate = new Intl.DateTimeFormat('en-GB', {
  timeZone: IST,
  day: 'numeric',
  month: 'short'
});

const crosshairStamp = new Intl.DateTimeFormat('en-GB', {
  timeZone: IST,
  weekday: 'short',
  day: 'numeric',
  month: 'short',
  year: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
  hour12: true
});

/**
 * `TickMarkType` as numbers: 0 Year, 1 Month, 2 DayOfMonth, 3 Time, 4 with
 * seconds. Compared numerically rather than against the imported enum, which is
 * a value import and would pull the library into the server bundle.
 */
const TICK_TIME = 3;

function tickLabel(seconds: number, tickMarkType: number): string {
  const ms = seconds * 1000;
  return tickMarkType >= TICK_TIME ? tickClock.format(ms) : tickDate.format(ms);
}

export default function LwChart({
  candles,
  volume,
  theme,
  type = 'candle',
  onHoverBar,
  handleRef,
  className,
  style
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  // Held across renders so data updates never rebuild the chart, and so the
  // cleanup below can dispose whatever the async mount produced.
  const api = useRef<{
    chart: IChartApi;
    price: ISeriesApi<SeriesType>;
    volume: ISeriesApi<'Histogram'> | undefined;
  } | null>(null);

  // Latest props for callbacks that are registered once at mount. Without this
  // the crosshair handler would report against the candles of the render it was
  // subscribed in, which is the first one.
  const latest = useRef({ candles, onHoverBar });
  latest.current = { candles, onHoverBar };

  const hasVolume = volume !== undefined;

  /**
   * Set when the library fails to load or the chart fails to build.
   *
   * Without this the component renders an empty `<div>` and the page looks like
   * a chart that has simply drawn nothing — indistinguishable from a data
   * problem, and silent in the console for anyone not looking. A dynamic import
   * really does fail in practice: a dev server that re-optimises its
   * dependencies invalidates the chunk under any tab that is already open.
   */
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    const el = container.current;
    if (!el) return;

    let disposed = false;

    void (async () => {
      const lib = await import('lightweight-charts').catch((error: unknown) => {
        if (!disposed) {
          console.error('[LwChart] the charting library failed to load', error);
          setFailed(true);
        }
        return null;
      });
      if (lib === null) return;

      const { createChart, CandlestickSeries, LineSeries, AreaSeries, HistogramSeries } = lib;
      // The component can unmount while the import is in flight.
      if (disposed || !container.current) return;
      setFailed(false);

      const chart = createChart(el, {
        // The library owns its own ResizeObserver under this flag, so there is
        // no second one here fighting it.
        autoSize: true,
        layout: {
          background: { color: 'transparent' },
          textColor: theme.axis,
          attributionLogo: false
        },
        grid: {
          vertLines: { color: theme.grid },
          horzLines: { color: theme.grid }
        },
        localization: {
          // The crosshair's own time label, which is formatted separately from
          // the axis ticks and would otherwise stay UTC.
          timeFormatter: (time: unknown) => crosshairStamp.format(Number(time) * 1000)
        },
        rightPriceScale: { borderColor: theme.grid },
        timeScale: {
          borderColor: theme.grid,
          timeVisible: true,
          secondsVisible: false,
          tickMarkFormatter: (time: unknown, tickMarkType: number) =>
            tickLabel(Number(time), tickMarkType)
        },
        crosshair: {
          vertLine: { color: theme.axis, labelBackgroundColor: theme.maxPainLabelBg },
          horzLine: { color: theme.axis, labelBackgroundColor: theme.maxPainLabelBg }
        }
      });

      const price =
        type === 'line'
          ? chart.addSeries(LineSeries, { color: theme.accent, lineWidth: 2 })
          : type === 'area'
            ? chart.addSeries(AreaSeries, { lineColor: theme.accent, lineWidth: 2 })
            : chart.addSeries(CandlestickSeries, {
                upColor: theme.call,
                downColor: theme.put,
                borderUpColor: theme.call,
                borderDownColor: theme.put,
                wickUpColor: theme.call,
                wickDownColor: theme.put
              });

      // Pane 1, not an overlay on the price scale: overlaid volume rescales the
      // candles every time turnover spikes.
      const volumeSeries = hasVolume
        ? chart.addSeries(HistogramSeries, { priceFormat: { type: 'volume' } }, 1)
        : undefined;
      if (volumeSeries && el.clientHeight > 0) {
        // Guarded: a zero-height container would collapse the pane to nothing
        // and the library keeps that height once set.
        chart.panes()[1]?.setHeight(el.clientHeight * VOLUME_PANE_FRACTION);
      }

      chart.subscribeCrosshairMove((param) => {
        const report = latest.current.onHoverBar;
        if (!report) return;
        // Off the plot entirely — fall back to the newest bar rather than
        // blanking the legend, which is what the reference does.
        if (param.time === undefined) return report(null);
        const at = Number(param.time);
        report(latest.current.candles.find((candle) => candle.time === at) ?? null);
      });

      api.current = { chart, price, volume: volumeSeries };
      if (handleRef) {
        handleRef.current = {
          screenshot: () => chart.takeScreenshot(),
          fitContent: () => chart.timeScale().fitContent()
        };
      }
      paint();
    })();

    return () => {
      disposed = true;
      api.current?.chart.remove();
      api.current = null;
      if (handleRef) handleRef.current = null;
    };
    // The container is stable for the component's lifetime, and theme changes
    // are applied below rather than by remounting — rebuilding the chart would
    // throw away the reader's zoom and scroll position. The series *type* is a
    // different matter: it is a different series object, so it does rebuild.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasVolume, type]);

  // -- data -----------------------------------------------------------------
  function paint(): void {
    const current = api.current;
    if (!current) return;

    if (type === 'candle') {
      current.price.setData(
        candles.map((candle) => ({
          time: candle.time as UTCTimestamp,
          open: candle.open,
          high: candle.high,
          low: candle.low,
          close: candle.close
        }))
      );
    } else {
      // Line and area plot one number a bar; the close is the one anyone means.
      current.price.setData(
        candles.map((candle) => ({ time: candle.time as UTCTimestamp, value: candle.close }))
      );
    }

    if (current.volume && volume) {
      current.volume.setData(
        volume.map((bar) => ({
          time: bar.time as UTCTimestamp,
          value: bar.value,
          color: bar.rising ? theme.call : theme.put
        }))
      );
    }

    current.chart.timeScale().fitContent();
  }

  useEffect(() => {
    paint();
    // `paint` closes over the latest props on every render, so listing it would
    // re-run this effect every time regardless.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candles, volume]);

  // -- theme ----------------------------------------------------------------
  useEffect(() => {
    const current = api.current;
    if (!current) return;

    // `applyOptions`, not a rebuild: a theme toggle must not reset the view.
    current.chart.applyOptions({
      layout: { textColor: theme.axis },
      grid: { vertLines: { color: theme.grid }, horzLines: { color: theme.grid } },
      rightPriceScale: { borderColor: theme.grid },
      timeScale: { borderColor: theme.grid }
    });
    if (type === 'candle') {
      current.price.applyOptions({
        upColor: theme.call,
        downColor: theme.put,
        borderUpColor: theme.call,
        borderDownColor: theme.put,
        wickUpColor: theme.call,
        wickDownColor: theme.put
      });
    } else {
      current.price.applyOptions({ color: theme.accent, lineColor: theme.accent });
    }
    // Volume bars carry their colour per point, so they are repainted rather
    // than re-optioned.
    paint();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);

  return (
    <div ref={container} className={cx(s.chart, className)} style={style}>
      {failed ? (
        <p className={s.failed} role="alert">
          The price chart could not load. Reload the page — if it persists after a hard reload, the
          charting library is failing to fetch.
        </p>
      ) : null}
    </div>
  );
}
