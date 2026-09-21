import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { useInstruments } from '$contexts/instrument-catalog/queries';
import { defaultInstrumentAt } from '$shared/config/instruments';
import type { ChartType, LwChartHandle } from '$shared/charts/tv/LwChart';
import { EMPTY_STATS, type DrawStats } from '$shared/charts/tv/drawings/useDrawings';
import { cx } from '$shared/ui/cx';
import ChartCell, { type DrawingHandle } from './components/ChartCell';
import DrawingRail from './components/DrawingRail';
import SymbolPicker from '$shared/ui/SymbolPicker';
import TopToolbar from './components/TopToolbar';
import { type Interval } from './analyse-data';
import type { IndicatorId } from './indicators';
import { cellsInLayout, defaultCell, type CellConfig, type LayoutId } from './workspace';
import s from './route.module.css';
import type { Route } from './+types/route';

/** Per-cell drawing state that isn't part of `CellConfig` — see `DrawingRail`'s docstring for why. */
interface DrawState {
  locked: boolean;
  visible: boolean;
}

const DEFAULT_DRAW_STATE: DrawState = { locked: false, visible: true };

export const meta: Route.MetaFunction = () => [{ title: 'Chart Tools · MarketCompass' }];

export default function Analyse() {
  const [layout, setLayout] = useState<LayoutId>('1');
  const [activeIdx, setActiveIdx] = useState(0);
  // Always four configs; the layout decides how many are on screen. Keeping the
  // hidden ones means switching to a 4-up grid and back does not reset them.
  const [cells, setCells] = useState<CellConfig[]>(() => [
    defaultCell(defaultInstrumentAt(0)),
    defaultCell(defaultInstrumentAt(1)),
    defaultCell(defaultInstrumentAt(2)),
    defaultCell(defaultInstrumentAt(0))
  ]);
  const [picking, setPicking] = useState(false);
  // The catalog is one cached fetch shared by the whole terminal, so asking
  // for it here costs nothing beyond the first page that did.
  const { instruments, isLoading: instrumentsLoading } = useInstruments();
  const [isFullscreen, setIsFullscreen] = useState(false);

  const workspace = useRef<HTMLDivElement>(null);
  // One stable handle per possible cell, for the toolbar's snapshot button.
  const h0 = useRef<LwChartHandle | null>(null);
  const h1 = useRef<LwChartHandle | null>(null);
  const h2 = useRef<LwChartHandle | null>(null);
  const h3 = useRef<LwChartHandle | null>(null);
  const handles = useMemo(() => [h0, h1, h2, h3], []);

  // -- drawings ---------------------------------------------------------------
  // The tool and magnet are "what happens on the next click", not a property
  // of any one cell, so they're uniform across the workspace. Lock/visible are
  // the opposite — properties of a cell's own drawings — so they're per cell,
  // parallel to `cells` but kept separate from `CellConfig`: see
  // `DrawingRail`'s docstring for why drawings aren't workspace config.
  const [tool, setTool] = useState<string | null>(null);
  const [magnet, setMagnet] = useState(false);
  // Reported up by whichever cell is focused, so the rail's counts and its
  // undo/redo enablement describe the chart the actions will land on.
  const [cellStats, setCellStats] = useState<DrawStats>(EMPTY_STATS);
  const [drawState, setDrawState] = useState<DrawState[]>(() =>
    cells.map(() => DEFAULT_DRAW_STATE)
  );
  const d0 = useRef<DrawingHandle | null>(null);
  const d1 = useRef<DrawingHandle | null>(null);
  const d2 = useRef<DrawingHandle | null>(null);
  const d3 = useRef<DrawingHandle | null>(null);
  const drawingHandles = useMemo(() => [d0, d1, d2, d3], []);

  const shown = cellsInLayout(layout);
  const active = cells[activeIdx] ?? cells[0]!;
  const activeDraw = drawState[activeIdx] ?? DEFAULT_DRAW_STATE;

  const patchDrawState = useCallback(
    (patch: Partial<DrawState>) => {
      setDrawState((prev) =>
        prev.map((entry, i) => (i === activeIdx ? { ...entry, ...patch } : entry))
      );
    },
    [activeIdx]
  );

  const patchActive = useCallback(
    (patch: Partial<CellConfig>) => {
      setCells((prev) => prev.map((cell, i) => (i === activeIdx ? { ...cell, ...patch } : cell)));
    },
    [activeIdx]
  );

  const toggleIndicator = useCallback(
    (id: IndicatorId) => {
      setCells((prev) =>
        prev.map((cell, i) => {
          if (i !== activeIdx) return cell;
          const on = cell.indicators.includes(id);
          return {
            ...cell,
            indicators: on
              ? cell.indicators.filter((entry) => entry !== id)
              : [...cell.indicators, id]
          };
        })
      );
    },
    [activeIdx]
  );

  const changeLayout = useCallback((next: LayoutId) => {
    setLayout(next);
    setActiveIdx((current) => Math.min(current, cellsInLayout(next) - 1));
  }, []);

  // -- fullscreen -----------------------------------------------------------
  useEffect(() => {
    function onChange() {
      setIsFullscreen(document.fullscreenElement === workspace.current);
    }
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);

  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void workspace.current?.requestFullscreen().catch(() => undefined);
  }, []);

  // Tool and magnet are page-owned — arming a tool arms every pane, so whichever
  // one the reader clicks next receives the shape. Everything else in the rail
  // describes the focused pane.
  const railStats = useMemo<DrawStats>(
    () => ({ ...cellStats, tool, magnet }),
    [cellStats, tool, magnet]
  );

  const onShortcut = useCallback(
    (event: KeyboardEvent): boolean => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'z') {
        const handle = drawingHandles[activeIdx]?.current;
        if (!handle) return false;
        if (event.shiftKey) handle.redo();
        else handle.undo();
        return true;
      }
      const armed = drawingHandles[activeIdx]?.current?.armByShortcut(event) ?? null;
      if (armed === null) return false;
      setTool(armed);
      return true;
    },
    [drawingHandles, activeIdx]
  );

  const snapshot = useCallback(() => {
    const canvas = handles[activeIdx]?.current?.screenshot();
    if (!canvas) return;
    const link = document.createElement('a');
    link.download = `${active.symbol}-${active.interval}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
  }, [handles, activeIdx, active.symbol, active.interval]);

  return (
    <div ref={workspace} className={s.workspace}>
      <TopToolbar
        interval={active.interval}
        onInterval={(value: Interval) => patchActive({ interval: value })}
        symbol={active.symbol}
        onOpenSymbols={() => setPicking(true)}
        chartType={active.chartType}
        onChartType={(value: ChartType) => patchActive({ chartType: value })}
        indicators={active.indicators}
        onToggleIndicator={toggleIndicator}
        layout={layout}
        onLayout={changeLayout}
        replay={active.replay}
        onToggleReplay={() => patchActive({ replay: !active.replay })}
        onSnapshot={snapshot}
        onFullscreen={toggleFullscreen}
        isFullscreen={isFullscreen}
      />

      <div className={s.body}>
        <DrawingRail
          stats={railStats}
          onPick={setTool}
          onUndo={() => drawingHandles[activeIdx]?.current?.undo()}
          onRedo={() => drawingHandles[activeIdx]?.current?.redo()}
          onRemove={(all) => drawingHandles[activeIdx]?.current?.remove(all)}
          onMagnet={setMagnet}
          locked={activeDraw.locked}
          onLocked={(on) => patchDrawState({ locked: on })}
          visible={activeDraw.visible}
          onVisible={(on) => patchDrawState({ visible: on })}
          portalHost={workspace.current}
          onShortcut={onShortcut}
        />

        <div className={cx(s.grid, s[`grid${layout}`])}>
          {cells.slice(0, shown).map((cell, index) => (
            <ChartCell
              key={index}
              config={cell}
              active={shown > 1 && index === activeIdx}
              onFocus={() => setActiveIdx(index)}
              onExitReplay={() =>
                setCells((prev) =>
                  prev.map((entry, i) => (i === index ? { ...entry, replay: false } : entry))
                )
              }
              handleRef={handles[index]}
              tool={tool}
              onToolDone={() => setTool(null)}
              magnet={magnet}
              locked={drawState[index]?.locked ?? false}
              drawingsVisible={drawState[index]?.visible ?? true}
              drawingHandleRef={drawingHandles[index]}
              onDrawStats={setCellStats}
              storageKey={`mc:analyse:cell${index}`}
            />
          ))}
        </div>
      </div>

      {picking ? (
        <SymbolPicker
          instruments={instruments}
          loading={instrumentsLoading}
          selected={active.symbol}
          onPick={(symbol) => patchActive({ symbol })}
          onClose={() => setPicking(false)}
        />
      ) : null}
    </div>
  );
}
