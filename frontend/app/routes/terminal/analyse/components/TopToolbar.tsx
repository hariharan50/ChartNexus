import { useEffect, useRef, useState, type ReactNode } from 'react';
import { cx } from '$shared/ui/cx';
import IconArea from '$shared/ui/icons/IconArea';
import IconBars from '$shared/ui/icons/IconBars';
import IconBaseline from '$shared/ui/icons/IconBaseline';
import IconCamera from '$shared/ui/icons/IconCamera';
import IconCandles from '$shared/ui/icons/IconCandles';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import IconHeikinAshi from '$shared/ui/icons/IconHeikinAshi';
import IconHighLow from '$shared/ui/icons/IconHighLow';
import IconHlcArea from '$shared/ui/icons/IconHlcArea';
import IconHollowCandles from '$shared/ui/icons/IconHollowCandles';
import IconLineBreak from '$shared/ui/icons/IconLineBreak';
import IconLineMarkers from '$shared/ui/icons/IconLineMarkers';
import IconRangeBars from '$shared/ui/icons/IconRangeBars';
import IconRenko from '$shared/ui/icons/IconRenko';
import IconStep from '$shared/ui/icons/IconStep';
import IconVolumeCandles from '$shared/ui/icons/IconVolumeCandles';
import IconExpand from '$shared/ui/icons/IconExpand';
import IconFx from '$shared/ui/icons/IconFx';
import IconGrid from '$shared/ui/icons/IconGrid';
import IconLayout from '$shared/ui/icons/IconLayout';
import IconLine from '$shared/ui/icons/IconLine';
import IconRedo from '$shared/ui/icons/IconRedo';
import IconReplay from '$shared/ui/icons/IconReplay';
import IconSave from '$shared/ui/icons/IconSave';
import IconSearch from '$shared/ui/icons/IconSearch';
import IconSettings from '$shared/ui/icons/IconSettings';
import IconUndo from '$shared/ui/icons/IconUndo';
import type { ChartType } from '$shared/charts/tv/LwChart';
import { INTERVALS, type Interval } from '../analyse-data';
import { type IndicatorId } from '../indicators';
import { LAYOUTS, type LayoutId } from '../workspace';
import IndicatorMenu from './IndicatorMenu';
import ToolbarMenu from './ToolbarMenu';
import s from './TopToolbar.module.css';

/**
 * The workspace's command strip.
 *
 * Controls that are wired are ordinary buttons. Controls whose feature has not
 * been built yet are rendered `disabled` with a `title` saying so, rather than
 * omitted: the reference's bar is a fixed shape people navigate by muscle
 * memory, and a button that silently does nothing is worse than one that says
 * it cannot yet.
 */
interface Props {
  interval: Interval;
  onInterval: (value: Interval) => void;
  symbol: string;
  onOpenSymbols: () => void;
  chartType: ChartType;
  onChartType: (value: ChartType) => void;
  indicators: IndicatorId[];
  onToggleIndicator: (id: IndicatorId) => void;
  layout: LayoutId;
  onLayout: (value: LayoutId) => void;
  replay: boolean;
  onToggleReplay: () => void;
  onSnapshot: () => void;
  onFullscreen: () => void;
  isFullscreen: boolean;
}

/**
 * One row of the chart-type menu. `value: null` is a type that is drawn in the
 * list but cannot be picked yet — see `soon`, and the note in this component's
 * docstring about why they are shown rather than omitted.
 */
interface ChartTypeEntry {
  value: ChartType | null;
  label: string;
  icon: ReactNode;
  soon?: string;
}

/**
 * The chart types, in three families: bar-shaped, line-shaped, and the ones
 * that redraw the series from the bars rather than restyling them.
 *
 * Grouped because the choice is really two choices — "how much of each bar do I
 * want to see" and "do I want the real bars at all" — and a flat list of
 * thirteen makes the second one invisible.
 */
const CHART_TYPE_GROUPS: ChartTypeEntry[][] = [
  [
    { value: 'bar', label: 'Bars (OHLC)', icon: <IconBars /> },
    { value: 'candle', label: 'Candles', icon: <IconCandles /> },
    { value: 'hollow', label: 'Hollow Candles', icon: <IconHollowCandles /> },
    {
      value: null,
      label: 'Volume Candles',
      icon: <IconVolumeCandles />,
      soon: 'Volume Candles — needs a custom series renderer, not built yet'
    },
    { value: 'highlow', label: 'High-Low', icon: <IconHighLow /> }
  ],
  [
    { value: 'line', label: 'Line', icon: <IconLine /> },
    { value: 'markers', label: 'Line + Markers', icon: <IconLineMarkers /> },
    { value: 'step', label: 'Step', icon: <IconStep /> },
    { value: 'area', label: 'Area', icon: <IconArea /> },
    {
      value: null,
      label: 'HLC Area',
      icon: <IconHlcArea />,
      soon: 'HLC Area — needs a custom series renderer, not built yet'
    },
    { value: 'baseline', label: 'Baseline', icon: <IconBaseline /> }
  ],
  [
    { value: 'heikin', label: 'Heikin Ashi', icon: <IconHeikinAshi /> },
    { value: 'renko', label: 'Renko', icon: <IconRenko /> },
    { value: 'range', label: 'Range Bars', icon: <IconRangeBars /> },
    { value: 'linebreak', label: 'Line Break', icon: <IconLineBreak /> }
  ]
];

const CHART_TYPES = CHART_TYPE_GROUPS.flat();

export default function TopToolbar({
  interval,
  onInterval,
  symbol,
  onOpenSymbols,
  chartType,
  onChartType,
  indicators,
  onToggleIndicator,
  layout,
  onLayout,
  replay,
  onToggleReplay,
  onSnapshot,
  onFullscreen,
  isFullscreen
}: Props) {
  const [openMenu, setOpenMenu] = useState<'interval' | 'type' | 'indicators' | 'layout' | null>(
    null
  );
  const bar = useRef<HTMLDivElement>(null);
  const intervalBtn = useRef<HTMLButtonElement>(null);
  const typeBtn = useRef<HTMLButtonElement>(null);
  const indicatorsBtn = useRef<HTMLButtonElement>(null);
  const layoutBtn = useRef<HTMLButtonElement>(null);

  // A menu left open behind a click elsewhere is a stuck overlay on a page
  // whose whole job is the area underneath it.
  useEffect(() => {
    if (openMenu === null) return;
    function onDown(event: MouseEvent) {
      const target = event.target as Node;
      if (bar.current?.contains(target)) return;
      // The open panel is portaled to `document.body` (see `ToolbarMenu`), so
      // it is never inside `bar` — without this it would read as an outside
      // click and close itself before its own item's `onClick` could fire.
      if ((target as Element).closest?.('[data-toolbar-menu]')) return;
      setOpenMenu(null);
    }
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') setOpenMenu(null);
    }
    document.addEventListener('mousedown', onDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [openMenu]);

  const activeType = CHART_TYPES.find((entry) => entry.value === chartType) ?? CHART_TYPES[0]!;

  return (
    <div ref={bar} className={s.bar} role="toolbar" aria-label="Chart controls">
      {/* interval */}
      <div className={s.menuWrap}>
        <button
          ref={intervalBtn}
          type="button"
          className={cx(s.btn, s.interval)}
          aria-haspopup="menu"
          aria-expanded={openMenu === 'interval'}
          onClick={() => setOpenMenu((m) => (m === 'interval' ? null : 'interval'))}
        >
          {INTERVALS.find((entry) => entry.value === interval)?.label ?? interval}
        </button>
        <ToolbarMenu anchorRef={intervalBtn} open={openMenu === 'interval'}>
          {INTERVALS.map((entry) => (
            <button
              key={entry.value}
              type="button"
              role="menuitemradio"
              aria-checked={entry.value === interval}
              className={cx(s.menuItem, entry.value === interval && s.menuItemOn)}
              onClick={() => {
                onInterval(entry.value);
                setOpenMenu(null);
              }}
            >
              <span>{entry.label}</span>
              <span className={s.menuHint}>
                {entry.days} {entry.days === 1 ? 'day' : 'days'}
              </span>
            </button>
          ))}
        </ToolbarMenu>
      </div>

      <span className={s.rule} aria-hidden="true" />

      {/* chart type */}
      <div className={s.menuWrap}>
        <button
          ref={typeBtn}
          type="button"
          className={s.btn}
          aria-haspopup="menu"
          aria-expanded={openMenu === 'type'}
          aria-label={`Chart type: ${activeType.label}`}
          onClick={() => setOpenMenu((m) => (m === 'type' ? null : 'type'))}
        >
          <span className={s.ico}>{activeType.icon}</span>
        </button>
        <ToolbarMenu anchorRef={typeBtn} open={openMenu === 'type'}>
          {CHART_TYPE_GROUPS.map((group, index) => (
            <div key={group[0]?.label ?? index} className={s.menuGroup} role="group">
              {index > 0 ? <span className={s.menuDivider} aria-hidden="true" /> : null}
              {group.map((entry) => (
                <button
                  key={entry.label}
                  type="button"
                  role="menuitemradio"
                  aria-checked={entry.value !== null && entry.value === chartType}
                  disabled={entry.value === null}
                  {...(entry.soon ? { title: entry.soon } : {})}
                  className={cx(s.menuItem, s.checkItem, entry.value === chartType && s.menuItemOn)}
                  onClick={() => {
                    if (entry.value === null) return;
                    onChartType(entry.value);
                    setOpenMenu(null);
                  }}
                >
                  <span className={s.ico}>{entry.icon}</span>
                  <span>{entry.label}</span>
                </button>
              ))}
            </div>
          ))}
        </ToolbarMenu>
      </div>

      <span className={s.rule} aria-hidden="true" />

      {/* indicators */}
      <div className={s.menuWrap}>
        <button
          ref={indicatorsBtn}
          type="button"
          className={cx(s.btn, indicators.length > 0 && s.btnOn)}
          aria-haspopup="menu"
          aria-expanded={openMenu === 'indicators'}
          onClick={() => setOpenMenu((m) => (m === 'indicators' ? null : 'indicators'))}
        >
          <span className={s.ico}>
            <IconFx />
          </span>
          <span className={s.btnText}>Indicators</span>
          {indicators.length > 0 ? (
            <span className={s.badge} aria-label={`${indicators.length} active`}>
              {indicators.length}
            </span>
          ) : null}
          <span className={s.caret} aria-hidden="true">
            <IconChevronDown />
          </span>
        </button>
        <ToolbarMenu
          anchorRef={indicatorsBtn}
          open={openMenu === 'indicators'}
          className={s.menuWide}
        >
          <IndicatorMenu active={indicators} onToggle={onToggleIndicator} />
        </ToolbarMenu>
      </div>
      <button type="button" className={s.btn} disabled title="Templates — not built yet">
        <span className={s.ico}>
          <IconGrid />
        </span>
      </button>

      <span className={s.rule} aria-hidden="true" />

      {/* symbol */}
      <button type="button" className={s.symbol} onClick={onOpenSymbols}>
        <span className={s.symbolIco} aria-hidden="true">
          <IconSearch />
        </span>
        <span className={s.symbolText}>
          <span className={s.symbolName}>{symbol}</span>
          <span className={s.symbolHint}>Click to change</span>
        </span>
      </button>

      <span className={s.rule} aria-hidden="true" />

      {/* layout */}
      <div className={s.menuWrap}>
        <button
          ref={layoutBtn}
          type="button"
          className={s.btn}
          aria-haspopup="menu"
          aria-expanded={openMenu === 'layout'}
          onClick={() => setOpenMenu((m) => (m === 'layout' ? null : 'layout'))}
        >
          <span className={s.ico}>
            <IconLayout />
          </span>
          <span className={s.btnText}>Layout</span>
        </button>
        <ToolbarMenu anchorRef={layoutBtn} open={openMenu === 'layout'}>
          {LAYOUTS.map((entry) => (
            <button
              key={entry.id}
              type="button"
              role="menuitemradio"
              aria-checked={entry.id === layout}
              className={cx(s.menuItem, entry.id === layout && s.menuItemOn)}
              onClick={() => {
                onLayout(entry.id);
                setOpenMenu(null);
              }}
            >
              <span>{entry.label}</span>
              <span className={s.menuHint}>
                {entry.cells} {entry.cells === 1 ? 'chart' : 'charts'}
              </span>
            </button>
          ))}
        </ToolbarMenu>
      </div>
      <button
        type="button"
        className={cx(s.btn, replay && s.btnOn)}
        onClick={onToggleReplay}
        aria-pressed={replay}
        title={replay ? 'Exit replay' : 'Replay the loaded session'}
      >
        <span className={s.ico}>
          <IconReplay />
        </span>
        <span className={s.btnText}>Replay</span>
      </button>

      <span className={s.rule} aria-hidden="true" />

      <button type="button" className={s.btn} disabled title="Undo — needs drawings">
        <span className={s.ico}>
          <IconUndo />
        </span>
      </button>
      <button type="button" className={s.btn} disabled title="Redo — needs drawings">
        <span className={s.ico}>
          <IconRedo />
        </span>
      </button>

      <span className={s.spacer} />

      <button type="button" className={cx(s.btn, s.save)} disabled title="Save — not built yet">
        <span className={s.ico}>
          <IconSave />
        </span>
        <span className={s.btnText}>Save</span>
        <span className={s.caret} aria-hidden="true">
          <IconChevronDown />
        </span>
      </button>
      <button type="button" className={s.btn} disabled title="Settings — not built yet">
        <span className={s.ico}>
          <IconSettings />
        </span>
      </button>
      <button
        type="button"
        className={s.btn}
        onClick={onFullscreen}
        aria-pressed={isFullscreen}
        title={isFullscreen ? 'Exit fullscreen' : 'Fullscreen'}
      >
        <span className={s.ico}>
          <IconExpand />
        </span>
      </button>
      <button type="button" className={s.btn} onClick={onSnapshot} title="Save a PNG snapshot">
        <span className={s.ico}>
          <IconCamera />
        </span>
      </button>
    </div>
  );
}
