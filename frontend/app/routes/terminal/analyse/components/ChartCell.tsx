import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState, type RefObject } from 'react';
import LwChart, { type Candle, type LwChartHandle } from '$shared/charts/tv/LwChart';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import {
  useDrawings,
  type DrawSelection,
  type DrawStats
} from '$shared/charts/tv/drawings/useDrawings';
import { preservesBars, transformCandles } from '$shared/charts/tv/series-transforms';
import { cx } from '$shared/ui/cx';
import { OI_INSTRUMENTS, REFETCH_MS } from '../../options/open-interest/oi-data';
import {
  getHistory,
  hasNoRealData,
  INTERVALS,
  toCandles,
  toVolume,
  type HistoryView
} from '../analyse-data';
import { buildOverlays } from '../indicators';
import { REPLAY_SPEEDS, type CellConfig, type ReplaySpeed } from '../workspace';
import ChartLegend from './ChartLegend';
import DrawingStyleBar from './DrawingStyleBar';
import DrawingTextDialog from './DrawingTextDialog';
import ReplayBar from './ReplayBar';
import s from './ChartCell.module.css';

/** Stable stand-in for an omitted callback, so it never re-identifies the controller's options. */
const noop = () => undefined;

/**
 * What the route can do to this cell's drawings.
 *
 * The rail is shared across a grid of cells, so the actions it fires have to
 * reach whichever cell was last drawn in — a ref rather than props, because the
 * route holds one of these per cell and only ever calls into the active one.
 */
export interface DrawingHandle {
  undo: () => void;
  redo: () => void;
  remove: (all: boolean) => void;
  armByShortcut: (event: KeyboardEvent) => string | null;
}

/**
 * One chart in the workspace: its own history query, indicators and replay head.
 *
 * Configuration is owned by the route (so the shared toolbar can drive whichever
 * cell is focused); everything downstream of it — the fetch, the candle
 * derivation, the replay position — lives here, so a four-up grid is four of
 * these running independently rather than one route juggling four of everything.
 */
interface Props {
  config: CellConfig;
  active: boolean;
  onFocus: () => void;
  onExitReplay: () => void;
  handleRef?: RefObject<LwChartHandle | null> | undefined;
  /** Registry tool id, or `null` for the plain cursor. */
  tool?: string | null | undefined;
  /** Every drawing tool is single-shot; this lands the toolbar back on the cursor. */
  onToolDone?: (() => void) | undefined;
  magnet?: boolean | undefined;
  locked?: boolean | undefined;
  drawingsVisible?: boolean | undefined;
  drawingHandleRef?: RefObject<DrawingHandle | null> | undefined;
  /** Reports this cell's drawing state up, so the shared rail can show it. */
  onDrawStats?: ((stats: DrawStats) => void) | undefined;
  /** Distinguishes this cell's saved drawings from its neighbours'. */
  storageKey: string;
}

export default function ChartCell({
  config,
  active,
  onFocus,
  onExitReplay,
  handleRef,
  tool = null,
  onToolDone,
  magnet = false,
  locked = false,
  drawingsVisible = true,
  drawingHandleRef,
  onDrawStats,
  storageKey
}: Props) {
  const theme = useChartTheme();
  // A cell always needs its own handle to attach drawings to, whether or not
  // the parent cares about screenshots/`fitContent` too — `handleRef` above is
  // optional for callers that don't.
  const ownHandleRef = useRef<LwChartHandle | null>(null);
  const chartHandleRef = handleRef ?? ownHandleRef;
  // The element the drawing host puts its pointer listeners on.
  const plotRef = useRef<HTMLDivElement>(null);
  const instrument =
    OI_INSTRUMENTS.find((entry) => entry.symbol === config.symbol) ?? OI_INSTRUMENTS[0]!;
  const timeframe = INTERVALS.find((entry) => entry.value === config.interval) ?? INTERVALS[1]!;

  const query = useQuery<HistoryView>({
    queryKey: ['market', 'history', config.symbol, config.interval, timeframe.days],
    queryFn: () => getHistory(config.symbol, config.interval, timeframe.days),
    // Replay is a frozen study of what was loaded; polling under it would shift
    // the bars beneath the playhead.
    refetchInterval: config.replay ? false : REFETCH_MS,
    placeholderData: (previous) => previous
  });

  const view = query.data;
  const allCandles = useMemo(() => toCandles(view), [view]);
  const allVolume = useMemo(() => toVolume(view), [view]);

  // -- replay ---------------------------------------------------------------
  const [head, setHead] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<ReplaySpeed>(REPLAY_SPEEDS[1]);

  // Entering replay parks the head on the last bar and starts playing from there
  // is wrong — you want to rewind and watch it build, so start at the open.
  useEffect(() => {
    if (config.replay) {
      setHead(0);
      setPlaying(true);
    } else {
      setPlaying(false);
    }
  }, [config.replay]);

  useEffect(() => {
    if (!config.replay || !playing) return;
    const id = window.setInterval(() => {
      setHead((h) => {
        if (h >= allCandles.length - 1) {
          setPlaying(false);
          return h;
        }
        return h + 1;
      });
    }, 1000 / speed);
    return () => window.clearInterval(id);
  }, [config.replay, playing, speed, allCandles.length]);

  // Memoised, not sliced inline: under replay a fresh array on every render
  // would invalidate the `overlays` memo below on every render too, so every
  // crosshair move (which sets `hovered`) would recompute every indicator over
  // the whole series and push a full `setData` at the chart. Identity is what
  // keeps that work tied to the playhead actually advancing.
  const visibleCandles = useMemo(
    () => (config.replay ? allCandles.slice(0, head + 1) : allCandles),
    [config.replay, allCandles, head]
  );
  const visibleVolume = useMemo(
    () => (config.replay && allVolume ? allVolume.slice(0, head + 1) : allVolume),
    [config.replay, allVolume, head]
  );

  // Heikin Ashi, Renko, Range Bars and Line Break redraw the series from the
  // feed's candles rather than restyling them — see `series-transforms.ts`.
  // Everything downstream works from the result, so the legend reads the bar
  // that is actually under the pointer and an indicator is computed from the
  // prices the reader can see. Every other type passes straight through.
  const drawnCandles = useMemo(
    () => transformCandles(config.chartType, visibleCandles),
    [config.chartType, visibleCandles]
  );

  // Renko and friends emit a bar per unit of *price movement*, so there is no
  // longer one bar per minute for a volume bar to sit under. Dropping the pane
  // is the honest answer; leaving it would draw turnover against bars it does
  // not belong to.
  const drawnVolume = preservesBars(config.chartType) ? visibleVolume : undefined;

  const overlays = useMemo(
    () => buildOverlays(new Set(config.indicators), drawnCandles, drawnVolume),
    [config.indicators, drawnCandles, drawnVolume]
  );

  const [hovered, setHovered] = useState<Candle | null>(null);
  const shownBar = hovered ?? drawnCandles[drawnCandles.length - 1] ?? null;
  const shownVolume = useMemo(() => {
    if (!drawnVolume || !shownBar) return null;
    return drawnVolume.find((bar) => bar.time === shownBar.time)?.value ?? null;
  }, [drawnVolume, shownBar]);

  const source = view?.provenance.source;

  // -- drawings ---------------------------------------------------------------
  // Whichever cell the reader actually clicks in draws on itself — there is no
  // need to gate this on `active`, since each cell listens to its own plot's
  // own pointer events independently.
  // Bumped when `LwChart` rebuilds its series (a chart-type switch), which is
  // what tells the host its chart and series went away.
  const [chartEpoch, setChartEpoch] = useState(0);
  const onChartReady = useCallback(() => setChartEpoch((n) => n + 1), []);

  const drawing = useDrawings({
    handleRef: chartHandleRef,
    containerRef: plotRef,
    // The bars actually on screen: the magnet has to snap to the candle the
    // reader can see, not the feed's version of it.
    candles: drawnCandles,
    theme,
    chartEpoch,
    storageKey,
    tool,
    magnet,
    locked,
    visible: drawingsVisible,
    onToolDone: onToolDone ?? noop
  });

  const { stats, selection, textRequest, undo, redo, remove, armByShortcut } = drawing;

  useEffect(() => {
    if (!drawingHandleRef) return;
    drawingHandleRef.current = { undo, redo, remove, armByShortcut };
    return () => {
      drawingHandleRef.current = null;
    };
  }, [drawingHandleRef, undo, redo, remove, armByShortcut]);

  // Only the focused cell drives the shared rail, or four cells would fight
  // over one set of counts.
  useEffect(() => {
    if (active) onDrawStats?.(stats);
  }, [active, stats, onDrawStats]);

  return (
    <div
      className={cx(s.cell, active && s.active)}
      onPointerDown={onFocus}
      role="group"
      aria-label={`${instrument.short} ${config.interval}`}
    >
      <div ref={plotRef} className={s.plot}>
        {query.isError ? (
          <div className={s.banner} role="alert">
            <span>Couldn’t load {instrument.short}.</span>
            <button type="button" onClick={() => void query.refetch()}>
              Retry
            </button>
          </div>
        ) : allCandles.length === 0 ? (
          <div className={s.empty}>
            {query.isPending ? (
              <p>Loading candles…</p>
            ) : hasNoRealData(view) ? (
              <>
                <p>No live data for {instrument.short} over this range.</p>
                {/* Named rather than implied: an empty chart reads as a bug,
                    and the reason this one is empty is a deliberate refusal. */}
                <p className={s.emptyHint}>
                  This chart draws only real broker data — never simulated bars. Connect a broker in
                  Settings, or pick a range the broker has.
                </p>
              </>
            ) : (
              <p>No candles yet.</p>
            )}
          </div>
        ) : (
          <>
            <ChartLegend
              symbol={instrument.short}
              badge={instrument.badge}
              bar={shownBar}
              volume={shownVolume}
            />
            <LwChart
              candles={drawnCandles}
              volume={drawnVolume}
              overlays={overlays}
              theme={theme}
              type={config.chartType}
              onHoverBar={setHovered}
              handleRef={chartHandleRef}
              onReady={onChartReady}
              resetKey={`${config.symbol}:${config.interval}:${config.chartType}`}
              className={s.chart}
            />
            <DrawingStyleBar
              selection={selection}
              onStyle={drawing.style}
              onEditText={drawing.editSelectedText}
              onDelete={() => remove(false)}
            />
            {textRequest ? (
              <DrawingTextDialog
                request={textRequest}
                onSubmit={drawing.applyText}
                onClose={drawing.closeText}
              />
            ) : null}
            {config.replay ? (
              <ReplayBar
                head={head}
                total={allCandles.length}
                playing={playing}
                speed={speed}
                onHead={(h) => {
                  setPlaying(false);
                  setHead(h);
                }}
                onPlaying={setPlaying}
                onSpeed={setSpeed}
                onExit={onExitReplay}
              />
            ) : null}
          </>
        )}
      </div>

      <div className={s.caption}>
        <span>
          {timeframe.label} · {allCandles.length} candles
          {source && source !== 'live' ? (
            <>
              {' · '}
              <span className={s.provenance}>
                {source === 'mock' ? 'simulated data' : 'cached data'}
              </span>
            </>
          ) : null}
        </span>
        <span
          className={cx(s.dot, query.isFetching && !config.replay && s.pulse)}
          aria-hidden="true"
        />
      </div>
    </div>
  );
}

export type { DrawSelection };
