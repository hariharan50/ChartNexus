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
  /**
   * The live chart and price series, for attaching custom drawings on top —
   * see `$shared/charts/tv/drawings`. A method rather than a stored pair:
   * both are rebuilt whenever `type` changes (candle/line/area), so a snapshot
   * taken once would go stale the next time the reader switches chart type.
   * `null` before the chart exists (the library is still loading).
   */
  getApi(): { chart: IChartApi; series: ISeriesApi<SeriesType> } | null;
}

/** One reconciled overlay line (indicator) drawn over the price or a sub-pane. */
export interface OverlaySpec {
  id: string;
  /** 0 = price pane, 1 = volume pane, ≥2 = a dedicated sub-pane (e.g. RSI). */
  paneIndex: number;
  color: string;
  lineWidth?: number;
  data: { time: number; value: number }[];
}

/**
 * One reconciled histogram drawn in a sub-pane, coloured per bar.
 *
 * The `volume` prop above is the one-histogram shortcut most pages want. This
 * is the general case: any number of them, on any pane, each bar carrying its
 * own colour — which is what a signed series (OI flow, delta, net turnover)
 * needs, since its sign changes bar to bar rather than following the candle's.
 *
 * Two specs may share a `paneIndex` to draw side by side, e.g. call and put
 * volume in one band.
 */
export interface HistogramSpec {
  id: string;
  /** 0 = price pane, ≥1 = a sub-pane. Sharing an index stacks two series in one band. */
  paneIndex: number;
  /**
   * Fraction of the chart's height this pane takes.
   *
   * Applied once, when the pane is created: the library keeps a height it has
   * been given, and re-applying it on every poll would fight a reader who has
   * dragged the divider.
   */
  paneFraction?: number;
  /**
   * How this pane's axis labels read.
   *
   * Without one the library formats the axis as a price — two decimals, no
   * grouping — so a pane of open interest is labelled `100000000.00`, which is
   * unreadable at a glance and is the wrong unit besides. Pass the same
   * formatter the legend uses so the axis and the readout agree.
   */
  format?: ((value: number) => string) | undefined;
  /** `value: null` leaves a genuine gap rather than drawing a zero-height bar. */
  data: { time: number; value: number | null; color: string }[];
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
  /** Indicator lines drawn over the price pane or a sub-pane; reconciled by id. */
  overlays?: OverlaySpec[] | undefined;
  /** Per-bar-coloured histograms in their own sub-panes; reconciled by id. */
  histograms?: HistogramSpec[] | undefined;
  /** Populated on mount, cleared on dispose. */
  handleRef?: RefObject<LwChartHandle | null> | undefined;
  /**
   * Fired every time a *new* chart and price series exist behind `handleRef` —
   * on mount, and again after a rebuild (a `type` switch, or volume appearing).
   *
   * Anything holding library objects obtained from `getApi()` has to know when
   * they have been thrown away: the old series is gone and whatever was attached
   * to it went with it. Without this signal a caller cannot tell a rebuild from
   * an ordinary re-render, and its attachments silently stop being drawn — see
   * `drawings/useDrawingController`, which re-attaches on this.
   */
  onReady?: (() => void) | undefined;
  /**
   * Identity of the drawn dataset — e.g. `"NIFTY:5m:candle"`. The view is fit to
   * the data **only when this changes**; across a live refetch it stays put, so a
   * poll never throws away the reader's zoom and scroll. Omit to fit on every
   * paint (the old, jumpy behaviour).
   */
  resetKey?: string | undefined;
  className?: string | undefined;
  style?: CSSProperties | undefined;
}

/** How much of the chart's height the volume pane takes, when there is one. */
const VOLUME_PANE_FRACTION = 0.22;
/** The pane index volume occupies (pane 0 is price). */
const VOLUME_PANE_INDEX = 1;

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

/**
 * Strictly ascending, duplicate-free by `time` — what the library requires and
 * throws on if violated. Keeps the *last* occurrence of a repeated timestamp,
 * on the assumption a later entry in the source array is the more current one.
 *
 * Returns the input array untouched when it is already in order, which is the
 * case on every single repaint of a well-behaved feed. This runs on the candles,
 * the volume bars and every indicator's points on each poll and each replay
 * tick, so the common path is a linear scan and no allocation at all rather than
 * a copy plus a sort of a few thousand bars several times a second.
 */
function sortAscending<T extends { time: number }>(items: T[]): T[] {
  let ordered = true;
  for (let i = 1; i < items.length; i += 1) {
    if (items[i]!.time <= items[i - 1]!.time) {
      ordered = false;
      break;
    }
  }
  if (ordered) return items;

  const sorted = [...items].sort((a, b) => a.time - b.time);
  const deduped: T[] = [];
  for (const item of sorted) {
    if (deduped.length > 0 && deduped[deduped.length - 1]!.time === item.time) {
      deduped[deduped.length - 1] = item;
    } else {
      deduped.push(item);
    }
  }
  return deduped;
}

export default function LwChart({
  candles,
  volume,
  theme,
  type = 'candle',
  onHoverBar,
  overlays,
  histograms,
  handleRef,
  onReady,
  resetKey,
  className,
  style
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  // Held across renders so data updates never rebuild the chart, and so the
  // cleanup below can dispose whatever the async mount produced. `addLine` is
  // the pane-aware line constructor captured from the dynamic import, and `lines`
  // is the id→series map the overlay reconciler keeps in step with the props.
  const api = useRef<{
    chart: IChartApi;
    price: ISeriesApi<SeriesType>;
    volume: ISeriesApi<'Histogram'> | undefined;
    addLine: (paneIndex: number) => ISeriesApi<'Line'>;
    lines: Map<string, ISeriesApi<'Line'>>;
    addHistogram: (paneIndex: number) => ISeriesApi<'Histogram'>;
    bars: Map<string, ISeriesApi<'Histogram'>>;
    /** Panes already given a height, so a poll never re-applies one. */
    sized: Set<number>;
  } | null>(null);

  // Latest props for callbacks that are registered once at mount. Without this
  // the crosshair handler would report against the candles of the render it was
  // subscribed in, which is the first one.
  const latest = useRef({ candles, onHoverBar, onReady });
  latest.current = { candles, onHoverBar, onReady };

  // The `resetKey` the view was last fit to. A refetch that keeps the same key
  // must not re-fit — that is what threw the reader's zoom away every poll.
  const lastFitKey = useRef<string | null>(null);

  const hasVolume = volume !== undefined;

  // Flips once `api.current` exists, so the data/overlay/histogram effects
  // below — which no-op while there is no chart to paint into — re-run against
  // *current* props as soon as one exists. Without this, a chart whose mount
  // effect is still awaiting the dynamic import can miss the one render where
  // fresh candles arrived: the data effect fires too early (no chart yet) and
  // never fires again once the import resolves, since `candles` itself hasn't
  // changed since. That left a correctly-sized, correctly-created canvas that
  // never drew anything — exactly the "empty grid" a newly added multi-chart
  // cell showed.
  const [ready, setReady] = useState(false);

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
      // A freshly built chart has no view yet, so the first paint must fit
      // whatever the current `resetKey` is.
      lastFitKey.current = null;

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

      api.current = {
        chart,
        price,
        volume: volumeSeries,
        addLine: (paneIndex: number) => chart.addSeries(LineSeries, {}, paneIndex),
        lines: new Map(),
        addHistogram: (paneIndex: number) => chart.addSeries(HistogramSeries, {}, paneIndex),
        bars: new Map(),
        sized: new Set(hasVolume ? [VOLUME_PANE_INDEX] : [])
      };
      if (handleRef) {
        handleRef.current = {
          screenshot: () => chart.takeScreenshot(),
          fitContent: () => chart.timeScale().fitContent(),
          getApi: () =>
            api.current ? { chart: api.current.chart, series: api.current.price } : null
        };
      }
      // Triggers the data/overlay/histogram effects below with whatever props
      // are current *then*, not the ones closed over here — see `ready` above.
      setReady(true);
      latest.current.onReady?.();
    })();

    return () => {
      disposed = true;
      setReady(false);
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

    // The library throws — uncatchably, past the render boundary — on a bar
    // out of order or repeated. The upstream feed is expected to already be
    // ascending, but a single reordered or duplicated bar (a session-boundary
    // edge case in a mock feed, a reordered response) must not take the whole
    // chart down with it; dropping it is a far smaller failure than a crash.
    const sortedCandles = sortAscending(candles);
    const sortedVolume = volume ? sortAscending(volume) : undefined;

    if (type === 'candle') {
      current.price.setData(
        sortedCandles.map((candle) => ({
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
        sortedCandles.map((candle) => ({ time: candle.time as UTCTimestamp, value: candle.close }))
      );
    }

    if (current.volume && sortedVolume) {
      current.volume.setData(
        sortedVolume.map((bar) => ({
          time: bar.time as UTCTimestamp,
          value: bar.value,
          color: bar.rising ? theme.call : theme.put
        }))
      );
    }

    // Fit only when the dataset identity changes — a new symbol, interval or
    // chart type. A same-key refetch keeps the reader's zoom and scroll, which
    // `setData` preserves on its own as long as we do not force a re-fit here.
    // With no `resetKey` given, fall back to fitting every paint (old behaviour).
    if (resetKey === undefined || lastFitKey.current !== resetKey) {
      current.chart.timeScale().fitContent();
      lastFitKey.current = resetKey ?? null;
    }
  }

  useEffect(() => {
    paint();
    // `paint` closes over the latest props on every render, so listing it would
    // re-run this effect every time regardless. `ready` is listed deliberately:
    // it is what makes this effect re-fire — this time against current props —
    // once the chart actually exists, rather than relying on the mount effect's
    // own stale-closure call.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candles, volume, ready]);

  // -- overlays (indicators) ------------------------------------------------
  /**
   * Bring the drawn line series in step with the `overlays` prop by id: update
   * the ones that stayed, add the ones that appeared, remove the ones that left.
   * Reconciling rather than clearing-and-readding means a live refetch repaints a
   * moving average in place instead of flashing it off and on every poll.
   */
  function reconcileOverlays(): void {
    const current = api.current;
    if (!current) return;
    const specs = overlays ?? [];
    const wanted = new Set(specs.map((spec) => spec.id));

    for (const [id, series] of current.lines) {
      if (!wanted.has(id)) {
        current.chart.removeSeries(series);
        current.lines.delete(id);
      }
    }

    for (const spec of specs) {
      let series = current.lines.get(spec.id);
      if (!series) {
        series = current.addLine(spec.paneIndex);
        current.lines.set(spec.id, series);
      }
      series.applyOptions({
        color: spec.color,
        lineWidth: (spec.lineWidth ?? 2) as 1 | 2 | 3 | 4,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false
      });
      // Same ascending/duplicate-free requirement `paint` guards against, and
      // the same reason: an indicator's points are derived from the candles,
      // so any disorder in the source data reaches here too.
      series.setData(
        sortAscending(spec.data).map((point) => ({
          time: point.time as UTCTimestamp,
          value: point.value
        }))
      );
    }

    // Keep any indicator sub-pane (e.g. RSI) to a slim band so it never crowds
    // the price. Volume owns its own height from mount; this only touches the
    // panes overlays actually occupy.
    const el = container.current;
    if (el && el.clientHeight > 0) {
      const subPanes = new Set(specs.filter((spec) => spec.paneIndex >= 1).map((s) => s.paneIndex));
      const panes = current.chart.panes();
      for (const index of subPanes) {
        // Skip the volume pane — it owns its height from mount. An overlay pane
        // that happens to be pane 1 because there is no volume is sized here.
        if (hasVolume && index === VOLUME_PANE_INDEX) continue;
        panes[index]?.setHeight(el.clientHeight * VOLUME_PANE_FRACTION);
      }
    }
  }

  useEffect(() => {
    reconcileOverlays();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [overlays, ready]);

  // -- histograms (signed sub-pane series) ----------------------------------
  /**
   * The same add/update/remove reconciliation the overlays get, for histograms.
   *
   * Colour lives on each point rather than on the series, because these are
   * signed: one bar is green and the next red within the same series, which a
   * series-level colour cannot express.
   *
   * A `null` value is dropped from the data rather than sent as `0`. The
   * library draws a zero-height bar for `0`, which on an OI-flow pane reads as
   * "nothing was written in this bar" — a claim the caller was careful not to
   * make when it sent `null` for "no observation here".
   */
  function reconcileHistograms(): void {
    const current = api.current;
    if (!current) return;
    const specs = histograms ?? [];
    const wanted = new Set(specs.map((spec) => spec.id));

    for (const [id, series] of current.bars) {
      if (!wanted.has(id)) {
        current.chart.removeSeries(series);
        current.bars.delete(id);
      }
    }

    const created: HistogramSpec[] = [];
    for (const spec of specs) {
      let series = current.bars.get(spec.id);
      if (!series) {
        series = current.addHistogram(spec.paneIndex);
        current.bars.set(spec.id, series);
        created.push(spec);
      }
      series.applyOptions({
        priceLineVisible: false,
        lastValueVisible: false,
        base: 0,
        ...(spec.format
          ? { priceFormat: { type: 'custom' as const, formatter: spec.format, minMove: 1 } }
          : {})
      });
      // Same ascending/duplicate-free requirement `paint` guards against.
      series.setData(
        sortAscending(spec.data.filter((point) => point.value !== null)).map((point) => ({
          time: point.time as UTCTimestamp,
          value: point.value as number,
          color: point.color
        }))
      );
    }

    // Sized after every series exists, and once per pane. Setting a height
    // while later panes are still being added lets the library redistribute it
    // out from under the pane that was just sized — which is how a band asked
    // for 20% ended up a sliver. Once, because the library keeps a height it
    // has been given and re-applying it every poll would fight a reader who has
    // dragged the divider.
    // Sized by stretch factor, not by `setHeight`.
    //
    // `setHeight` is absolute, but the library implements it by recomputing
    // every pane's stretch factor — so with more than one sub-pane each call
    // undoes the last, and whichever was sized first ends up a sliver
    // regardless of the order. Stretch factors are the declarative form of the
    // same thing: state the whole split at once and there is no sequence to get
    // wrong. Applied once per pane, so a reader dragging a divider keeps it.
    const fresh = created.filter(
      (spec) => spec.paneFraction !== undefined && !current.sized.has(spec.paneIndex)
    );
    if (fresh.length > 0) {
      const shares = new Map<number, number>();
      for (const spec of specs) {
        if (spec.paneFraction !== undefined) shares.set(spec.paneIndex, spec.paneFraction);
      }
      const panes = current.chart.panes();
      let taken = 0;
      for (const [index, share] of shares) {
        panes[index]?.setStretchFactor(share * 100);
        taken += share;
      }
      // Whatever is left goes to price, floored so a caller asking for more
      // than the whole chart cannot collapse it entirely.
      panes[0]?.setStretchFactor(Math.max(0.15, 1 - taken) * 100);
      for (const spec of fresh) current.sized.add(spec.paneIndex);
    }
  }

  useEffect(() => {
    reconcileHistograms();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [histograms, ready]);

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
