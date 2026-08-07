import { useEffect, useRef, useState, type ReactNode } from 'react';
import { cx } from '$shared/ui/cx';
import IconArea from '$shared/ui/icons/IconArea';
import IconCamera from '$shared/ui/icons/IconCamera';
import IconCandles from '$shared/ui/icons/IconCandles';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
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
  onSnapshot: () => void;
  onFullscreen: () => void;
  isFullscreen: boolean;
}

const CHART_TYPES: { value: ChartType; label: string; icon: ReactNode }[] = [
  { value: 'candle', label: 'Candles', icon: <IconCandles /> },
  { value: 'line', label: 'Line', icon: <IconLine /> },
  { value: 'area', label: 'Area', icon: <IconArea /> }
];

export default function TopToolbar({
  interval,
  onInterval,
  symbol,
  onOpenSymbols,
  chartType,
  onChartType,
  onSnapshot,
  onFullscreen,
  isFullscreen
}: Props) {
  const [openMenu, setOpenMenu] = useState<'interval' | 'type' | null>(null);
  const bar = useRef<HTMLDivElement>(null);

  // A menu left open behind a click elsewhere is a stuck overlay on a page
  // whose whole job is the area underneath it.
  useEffect(() => {
    if (openMenu === null) return;
    function onDown(event: MouseEvent) {
      if (!bar.current?.contains(event.target as Node)) setOpenMenu(null);
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
          type="button"
          className={cx(s.btn, s.interval)}
          aria-haspopup="menu"
          aria-expanded={openMenu === 'interval'}
          onClick={() => setOpenMenu((m) => (m === 'interval' ? null : 'interval'))}
        >
          {INTERVALS.find((entry) => entry.value === interval)?.label ?? interval}
        </button>
        {openMenu === 'interval' ? (
          <div className={s.menu} role="menu">
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
          </div>
        ) : null}
      </div>

      <span className={s.rule} aria-hidden="true" />

      {/* chart type */}
      <div className={s.menuWrap}>
        <button
          type="button"
          className={s.btn}
          aria-haspopup="menu"
          aria-expanded={openMenu === 'type'}
          aria-label={`Chart type: ${activeType.label}`}
          onClick={() => setOpenMenu((m) => (m === 'type' ? null : 'type'))}
        >
          <span className={s.ico}>{activeType.icon}</span>
        </button>
        {openMenu === 'type' ? (
          <div className={s.menu} role="menu">
            {CHART_TYPES.map((entry) => (
              <button
                key={entry.value}
                type="button"
                role="menuitemradio"
                aria-checked={entry.value === chartType}
                className={cx(s.menuItem, entry.value === chartType && s.menuItemOn)}
                onClick={() => {
                  onChartType(entry.value);
                  setOpenMenu(null);
                }}
              >
                <span className={s.ico}>{entry.icon}</span>
                <span>{entry.label}</span>
              </button>
            ))}
          </div>
        ) : null}
      </div>

      <span className={s.rule} aria-hidden="true" />

      <button type="button" className={s.btn} disabled title="Indicators — not built yet">
        <span className={s.ico}>
          <IconFx />
        </span>
        <span className={s.btnText}>Indicators</span>
      </button>
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

      <button type="button" className={s.btn} disabled title="Layout — not built yet">
        <span className={s.ico}>
          <IconLayout />
        </span>
        <span className={s.btnText}>Layout</span>
      </button>
      <button type="button" className={s.btn} disabled title="Replay — not built yet">
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
