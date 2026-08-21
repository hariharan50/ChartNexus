import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { cx } from '$shared/ui/cx';
import type { DrawStats } from '$shared/charts/tv/drawings/useDrawings';
import { DRAW_GROUPS, groupOf, type DrawGroupDef } from '../draw-catalogue';
import { drawToolIcon } from '../draw-icons';
import s from './DrawingRail.module.css';

/**
 * The left-hand drawing rail: 43 tools behind eight buttons.
 *
 * A flush column with a right border rather than a floating card, so the plot
 * begins where the rail ends and nothing the chart paints can sit underneath
 * it.
 *
 * The group buttons are what make eight buttons cover 43 tools. Each one
 * remembers the last tool picked from it, so a plain click re-arms that tool
 * and the reader is not made to walk a menu every time they want another trend
 * line. Reaching a *different* tool in the group is the caret wedge in the
 * corner, which opens the flyout without disturbing what is armed.
 */
interface Props {
  stats: DrawStats;
  onPick: (toolId: string | null) => void;
  onUndo: () => void;
  onRedo: () => void;
  onRemove: (all: boolean) => void;
  onMagnet: (on: boolean) => void;
  locked: boolean;
  onLocked: (on: boolean) => void;
  visible: boolean;
  onVisible: (on: boolean) => void;
  /**
   * Where the flyout renders. The workspace element, which is also the
   * Fullscreen target — a menu portalled to `document.body` is invisible while
   * anything else is in the top layer, so in fullscreen no tool could be picked
   * at all.
   */
  portalHost?: HTMLElement | null;
  /** Returns the tool a keystroke armed, or null. Kept out here so the rail never imports the engine. */
  onShortcut?: (event: KeyboardEvent) => boolean;
}

export default function DrawingRail({
  stats,
  onPick,
  onUndo,
  onRedo,
  onRemove,
  onMagnet,
  locked,
  onLocked,
  visible,
  onVisible,
  portalHost,
  onShortcut
}: Props) {
  const [openGroup, setOpenGroup] = useState<string | null>(null);
  const [anchor, setAnchor] = useState<{ top: number; left: number } | null>(null);
  // The last tool picked from each group, so the button re-arms rather than
  // re-asking.
  const lastRef = useRef<Record<string, string>>({});
  const activeGroup = groupOf(stats.tool);

  const openFlyout = useCallback((key: string, button: HTMLElement) => {
    const rect = button.getBoundingClientRect();
    setAnchor({ top: rect.top, left: rect.right + 6 });
    setOpenGroup(key);
  }, []);

  const pick = useCallback(
    (groupKey: string, toolId: string) => {
      lastRef.current[groupKey] = toolId;
      setOpenGroup(null);
      onPick(stats.tool === toolId ? null : toolId);
    },
    [onPick, stats.tool]
  );

  const onGroupClick = useCallback(
    (group: DrawGroupDef, event: React.MouseEvent<HTMLButtonElement>) => {
      const remembered = lastRef.current[group.key];
      if (remembered) {
        onPick(stats.tool === remembered ? null : remembered);
        return;
      }
      openFlyout(group.key, event.currentTarget);
    },
    [onPick, openFlyout, stats.tool]
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        if (openGroup) {
          setOpenGroup(null);
          return;
        }
        if (stats.tool) {
          onPick(null);
          return;
        }
      }
      // Never steal a keystroke from a field the reader is typing in.
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(target.tagName))
      ) {
        return;
      }
      if (onShortcut?.(event)) event.preventDefault();
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [stats.tool, onPick, onShortcut, openGroup]);

  return (
    <div className={s.rail} role="toolbar" aria-label="Drawing tools" aria-orientation="vertical">
      <RailButton
        label="Cursor"
        chord="Esc"
        icon="cursor"
        on={stats.tool === null}
        onClick={() => onPick(null)}
      />

      <span className={s.rule} aria-hidden="true" />

      {DRAW_GROUPS.map((group) => (
        <div key={group.key} className={s.group}>
          <RailButton
            label={group.label}
            icon={group.iconKey}
            on={activeGroup === group.key}
            suppressTip={openGroup === group.key}
            expanded={openGroup === group.key}
            onClick={(event) => onGroupClick(group, event)}
            onContextMenu={(event) => {
              event.preventDefault();
              openFlyout(group.key, event.currentTarget);
            }}
          />
          {/* A filled corner triangle, not a chevron: at eight pixels a
              chevron's strokes blur into a smudge, where the wedge reads as
              "there is more here" without competing with the glyph above it. */}
          <button
            type="button"
            className={s.caret}
            aria-label={`More ${group.label.toLowerCase()} tools`}
            onClick={(event) => {
              event.stopPropagation();
              openFlyout(group.key, event.currentTarget.parentElement as HTMLElement);
            }}
          >
            <svg viewBox="0 0 10 10" width="10" height="10" aria-hidden="true">
              <path d="M10 2 10 10 2 10 Z" fill="currentColor" />
            </svg>
          </button>
        </div>
      ))}

      <span className={s.rule} aria-hidden="true" />

      <RailButton
        label={stats.magnet ? 'Magnet: snapping to candles' : 'Magnet: off'}
        icon="magnet"
        on={stats.magnet}
        onClick={() => onMagnet(!stats.magnet)}
      />
      <RailButton
        label={locked ? 'Unlock drawings' : 'Lock drawings'}
        icon={locked ? 'lock' : 'unlock'}
        on={locked}
        onClick={() => onLocked(!locked)}
      />
      <RailButton
        label={visible ? 'Hide drawings' : 'Show drawings'}
        icon={visible ? 'eye' : 'eyeoff'}
        on={!visible}
        onClick={() => onVisible(!visible)}
      />
      <RailButton
        label="Undo"
        chord="Ctrl + Z"
        icon="undo"
        disabled={!stats.canUndo}
        onClick={onUndo}
      />
      <RailButton
        label="Redo"
        chord="Ctrl + Shift + Z"
        icon="redo"
        disabled={!stats.canRedo}
        onClick={onRedo}
      />
      <RailButton
        label={stats.hasSelection ? 'Delete selected' : `Remove all (${stats.count})`}
        icon="trash"
        disabled={stats.count === 0}
        onClick={() => onRemove(!stats.hasSelection)}
      />

      {openGroup && anchor ? (
        <Flyout
          group={DRAW_GROUPS.find((g) => g.key === openGroup)!}
          anchor={anchor}
          activeTool={stats.tool}
          shortcuts={stats.shortcuts}
          host={portalHost ?? null}
          onPick={pick}
          onClose={() => setOpenGroup(null)}
        />
      ) : null}
    </div>
  );
}

interface ButtonProps {
  label: string;
  icon: string;
  chord?: string;
  on?: boolean;
  disabled?: boolean;
  expanded?: boolean;
  suppressTip?: boolean;
  onClick: (event: React.MouseEvent<HTMLButtonElement>) => void;
  onContextMenu?: (event: React.MouseEvent<HTMLButtonElement>) => void;
}

function RailButton({
  label,
  icon,
  chord,
  on = false,
  disabled = false,
  expanded,
  suppressTip = false,
  onClick,
  onContextMenu
}: ButtonProps) {
  return (
    <button
      type="button"
      className={cx(s.btn, on && s.on)}
      aria-label={label}
      aria-pressed={on}
      {...(expanded === undefined ? {} : { 'aria-expanded': expanded })}
      disabled={disabled}
      onClick={onClick}
      {...(onContextMenu ? { onContextMenu } : {})}
    >
      {drawToolIcon(icon)}
      {/* Not the native `title` attribute: it waits about a second before
          appearing and cannot be styled, and a column of near-identical glyphs
          needs its names immediately. */}
      {suppressTip ? null : (
        <span className={s.tip} aria-hidden="true">
          {label}
          {chord ? <span className={s.tipChord}>{chord}</span> : null}
        </span>
      )}
    </button>
  );
}

interface FlyoutProps {
  group: DrawGroupDef;
  anchor: { top: number; left: number };
  activeTool: string | null;
  shortcuts: Record<string, string>;
  host: HTMLElement | null;
  onPick: (groupKey: string, toolId: string) => void;
  onClose: () => void;
}

function Flyout({ group, anchor, activeTool, shortcuts, host, onPick, onClose }: FlyoutProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const [top, setTop] = useState(anchor.top);

  // Clamp to the viewport once the panel has a measured height, so a group near
  // the bottom of a short window opens upwards instead of off screen.
  useLayoutEffect(() => {
    const height = panelRef.current?.offsetHeight ?? 0;
    const max = window.innerHeight - height - 8;
    setTop(Math.max(8, Math.min(anchor.top, max)));
  }, [anchor.top]);

  useEffect(() => {
    function onDown(event: MouseEvent) {
      if (!panelRef.current?.contains(event.target as Node)) onClose();
    }
    // Deferred a frame: the click that opened this would otherwise close it.
    const id = window.setTimeout(() => document.addEventListener('mousedown', onDown), 0);
    return () => {
      window.clearTimeout(id);
      document.removeEventListener('mousedown', onDown);
    };
  }, [onClose]);

  const panel = (
    <div
      ref={panelRef}
      className={s.flyout}
      style={{ top, left: anchor.left }}
      role="menu"
      aria-label={group.label}
    >
      {group.sections.map((section, index) => (
        <div key={section.head ?? index} className={index === 0 ? undefined : s.sectionGap}>
          {section.head ? <p className={s.sectionHead}>{section.head}</p> : null}
          {section.tools.map((tool) => (
            <button
              key={tool.id}
              type="button"
              role="menuitemradio"
              aria-checked={activeTool === tool.id}
              className={cx(s.row, activeTool === tool.id && s.rowOn)}
              onClick={() => tool.id && onPick(group.key, tool.id)}
            >
              <span className={s.rowIcon}>{drawToolIcon(tool.iconKey, 16)}</span>
              <span className={s.rowLabel}>{tool.label}</span>
              {tool.id && shortcuts[tool.id] ? (
                <span className={s.rowChord}>{shortcuts[tool.id]!.replace('+', ' + ')}</span>
              ) : null}
            </button>
          ))}
        </div>
      ))}
    </div>
  );

  return host ? createPortal(panel, host) : panel;
}
