import type { ReactNode } from 'react';
import { cx } from '$shared/ui/cx';
import IconCrosshair from '$shared/ui/icons/IconCrosshair';
import IconEye from '$shared/ui/icons/IconEye';
import IconEyeOff from '$shared/ui/icons/IconEyeOff';
import IconFibonacci from '$shared/ui/icons/IconFibonacci';
import IconHorizontalLine from '$shared/ui/icons/IconHorizontalLine';
import IconLock from '$shared/ui/icons/IconLock';
import IconMagnet from '$shared/ui/icons/IconMagnet';
import IconRectangle from '$shared/ui/icons/IconRectangle';
import IconRuler from '$shared/ui/icons/IconRuler';
import IconTextTool from '$shared/ui/icons/IconTextTool';
import IconTrash from '$shared/ui/icons/IconTrash';
import IconTrendLine from '$shared/ui/icons/IconTrendLine';
import type { DrawingTool } from '$shared/charts/tv/drawings/types';
import s from './DrawingToolbar.module.css';

const TOOLS: { id: DrawingTool; label: string; icon: ReactNode }[] = [
  { id: 'trendline', label: 'Trend line', icon: <IconTrendLine /> },
  { id: 'horizontal', label: 'Horizontal line', icon: <IconHorizontalLine /> },
  { id: 'fib', label: 'Fibonacci retracement', icon: <IconFibonacci /> },
  { id: 'rectangle', label: 'Rectangle', icon: <IconRectangle /> },
  { id: 'text', label: 'Text', icon: <IconTextTool /> },
  { id: 'measure', label: 'Measure', icon: <IconRuler /> }
];

/**
 * The left-hand drawing rail — the tool list on top, toggles and the clear
 * action below, matching the reference chart's own layout.
 *
 * A vertical sibling of `TopToolbar`, not a variant of it: that toolbar picks
 * one of a fixed set of *settings* (interval, chart type), where this one
 * picks one of a fixed set of *actions to take on the next click on the
 * chart* — the interaction model is different enough that sharing markup
 * would only have coupled two things that change for different reasons.
 */
interface Props {
  tool: DrawingTool | null;
  onTool: (tool: DrawingTool | null) => void;
  magnet: boolean;
  onMagnet: () => void;
  locked: boolean;
  onLocked: () => void;
  visible: boolean;
  onVisible: () => void;
  onClear: () => void;
}

export default function DrawingToolbar({
  tool,
  onTool,
  magnet,
  onMagnet,
  locked,
  onLocked,
  visible,
  onVisible,
  onClear
}: Props) {
  return (
    <div className={s.rail} role="toolbar" aria-label="Drawing tools" aria-orientation="vertical">
      <button
        type="button"
        className={cx(s.btn, tool === null && s.active)}
        title="Cursor"
        aria-pressed={tool === null}
        onClick={() => onTool(null)}
      >
        <IconCrosshair />
      </button>

      <span className={s.rule} aria-hidden="true" />

      {TOOLS.map((entry) => (
        <button
          key={entry.id}
          type="button"
          className={cx(s.btn, tool === entry.id && s.active)}
          title={entry.label}
          aria-pressed={tool === entry.id}
          onClick={() => onTool(tool === entry.id ? null : entry.id)}
        >
          {entry.icon}
        </button>
      ))}

      <span className={s.spacer} />

      <button
        type="button"
        className={cx(s.btn, magnet && s.active)}
        title={magnet ? 'Magnet: snapping to candles' : 'Magnet: off'}
        aria-pressed={magnet}
        onClick={onMagnet}
      >
        <IconMagnet />
      </button>
      <button
        type="button"
        className={cx(s.btn, locked && s.active)}
        title={locked ? 'Unlock drawings' : 'Lock drawings'}
        aria-pressed={locked}
        onClick={onLocked}
      >
        <IconLock />
      </button>
      <button
        type="button"
        className={s.btn}
        title={visible ? 'Hide drawings' : 'Show drawings'}
        aria-pressed={!visible}
        onClick={onVisible}
      >
        {visible ? <IconEye /> : <IconEyeOff />}
      </button>
      <button
        type="button"
        className={s.btn}
        // Locked drawings refuse to be cleared (the controller enforces it);
        // the button says so rather than swallowing the click silently.
        disabled={locked}
        title={locked ? 'Unlock to clear drawings' : 'Clear all drawings on this chart'}
        onClick={() => {
          if (window.confirm('Clear every drawing on this chart?')) onClear();
        }}
      >
        <IconTrash />
      </button>
    </div>
  );
}
