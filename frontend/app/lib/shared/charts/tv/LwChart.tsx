import { useEffect, useRef, type CSSProperties } from 'react';
import { cx } from '$shared/ui/cx';
// `import type`, never a value import. Type-only imports are erased entirely at
// compile time, so this costs nothing at runtime and — critically — does not
// pull the library into the server bundle. See the note on SSR below.
import type { IChartApi, ISeriesApi, UTCTimestamp } from 'lightweight-charts';
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

interface Props {
  candles: Candle[];
  /** Omit for a price-only chart; an empty array draws an empty pane. */
  volume?: VolumeBar[] | undefined;
  theme: ChartTheme;
  className?: string | undefined;
  style?: CSSProperties | undefined;
}

/** How much of the chart's height the volume pane takes, when there is one. */
const VOLUME_PANE_FRACTION = 0.22;

export default function LwChart({ candles, volume, theme, className, style }: Props) {
  const container = useRef<HTMLDivElement>(null);
  // Held across renders so data updates never rebuild the chart, and so the
  // cleanup below can dispose whatever the async mount produced.
  const api = useRef<{
    chart: IChartApi;
    price: ISeriesApi<'Candlestick'>;
    volume: ISeriesApi<'Histogram'> | undefined;
  } | null>(null);

  const hasVolume = volume !== undefined;

  useEffect(() => {
    const el = container.current;
    if (!el) return;

    let disposed = false;

    void (async () => {
      const { createChart, CandlestickSeries, HistogramSeries } =
        await import('lightweight-charts');
      // The component can unmount while the import is in flight.
      if (disposed || !container.current) return;

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
        rightPriceScale: { borderColor: theme.grid },
        timeScale: { borderColor: theme.grid, timeVisible: true, secondsVisible: false },
        crosshair: {
          vertLine: { color: theme.axis, labelBackgroundColor: theme.maxPainLabelBg },
          horzLine: { color: theme.axis, labelBackgroundColor: theme.maxPainLabelBg }
        }
      });

      const price = chart.addSeries(CandlestickSeries, {
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

      api.current = { chart, price, volume: volumeSeries };
      paint();
    })();

    return () => {
      disposed = true;
      api.current?.chart.remove();
      api.current = null;
    };
    // The container is stable for the component's lifetime, and theme changes
    // are applied below rather than by remounting — rebuilding the chart would
    // throw away the reader's zoom and scroll position.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasVolume]);

  // -- data -----------------------------------------------------------------
  function paint(): void {
    const current = api.current;
    if (!current) return;

    current.price.setData(
      candles.map((candle) => ({
        time: candle.time as UTCTimestamp,
        open: candle.open,
        high: candle.high,
        low: candle.low,
        close: candle.close
      }))
    );

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
    current.price.applyOptions({
      upColor: theme.call,
      downColor: theme.put,
      borderUpColor: theme.call,
      borderDownColor: theme.put,
      wickUpColor: theme.call,
      wickDownColor: theme.put
    });
    // Volume bars carry their colour per point, so they are repainted rather
    // than re-optioned.
    paint();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [theme]);

  return <div ref={container} className={cx(s.chart, className)} style={style} />;
}
