import { useEffect, useRef, useState } from 'react';
import { cx } from '$shared/ui/cx';
import type { DrawSelection } from '$shared/charts/tv/drawings/useDrawings';
import { drawToolIcon } from '../draw-icons';
import s from './DrawingStyleBar.module.css';

const SWATCHES = [
  '#4f8cff',
  '#26a69a',
  '#ef5350',
  '#f5a623',
  '#ab47bc',
  '#26c6da',
  '#9aa0b4',
  '#ffffff'
];
const WIDTHS = [1, 1.5, 2, 3, 4];
const DASHES = [
  { value: 'solid', label: '──' },
  { value: 'dashed', label: '- -' },
  { value: 'dotted', label: '···' }
];

/**
 * The floating toolbar that appears with a selection and goes with it.
 *
 * Positioned inside the pane rather than portalled to `document.body`, for the
 * same reason the rail's flyout is: `document.body` is invisible while the
 * workspace is in the Fullscreen top layer.
 */
interface Props {
  selection: DrawSelection | null;
  onStyle: (patch: {
    color?: string;
    lineWidth?: number;
    lineStyle?: string;
    locked?: boolean;
  }) => void;
  onEditText: () => void;
  onDelete: () => void;
}

type Popover = 'color' | 'width' | 'dash' | null;

export default function DrawingStyleBar({ selection, onStyle, onEditText, onDelete }: Props) {
  const [open, setOpen] = useState<Popover>(null);
  const barRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function onDown(event: MouseEvent) {
      if (!barRef.current?.contains(event.target as Node)) setOpen(null);
    }
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  // Nothing selected, nothing to style. Rendering an empty bar would leave a
  // control pointed at no object.
  if (!selection) return null;

  const dash = DASHES.find((entry) => entry.value === selection.lineStyle) ?? DASHES[0]!;

  return (
    <div
      ref={barRef}
      className={s.bar}
      role="toolbar"
      aria-label="Drawing style"
      // Marks this as a chart overlay so the drawing host ignores pointer events
      // that bubble from these buttons — otherwise the click that fires a button
      // also deselects the drawing the button acts on. See `lw-host.ts`.
      data-mc-chart-overlay=""
    >
      <div className={s.slot}>
        <button
          type="button"
          className={s.btn}
          aria-label="Colour"
          aria-expanded={open === 'color'}
          onClick={() => setOpen(open === 'color' ? null : 'color')}
        >
          <span className={s.swatch} style={{ background: selection.color }} />
        </button>
        {open === 'color' ? (
          <div className={s.popover}>
            <div className={s.swatchGrid}>
              {SWATCHES.map((color) => (
                <button
                  key={color}
                  type="button"
                  className={cx(s.swatchBtn, selection.color === color && s.swatchOn)}
                  style={{ background: color }}
                  aria-label={color}
                  onClick={() => {
                    onStyle({ color });
                    setOpen(null);
                  }}
                />
              ))}
            </div>
          </div>
        ) : null}
      </div>

      <div className={s.slot}>
        <button
          type="button"
          className={s.btn}
          aria-label="Thickness"
          aria-expanded={open === 'width'}
          onClick={() => setOpen(open === 'width' ? null : 'width')}
        >
          <span className={s.btnText}>{selection.lineWidth}px</span>
        </button>
        {open === 'width' ? (
          <div className={s.popover}>
            {WIDTHS.map((width) => (
              <button
                key={width}
                type="button"
                className={cx(s.listRow, selection.lineWidth === width && s.listRowOn)}
                onClick={() => {
                  onStyle({ lineWidth: width });
                  setOpen(null);
                }}
              >
                {/* The sample is drawn at the width it selects — the number
                    alone does not tell you what 3px looks like on this chart. */}
                <span className={s.widthBar} style={{ height: `${width}px` }} />
                <span>{width}px</span>
              </button>
            ))}
          </div>
        ) : null}
      </div>

      <div className={s.slot}>
        <button
          type="button"
          className={s.btn}
          aria-label="Line style"
          aria-expanded={open === 'dash'}
          onClick={() => setOpen(open === 'dash' ? null : 'dash')}
        >
          <span className={s.btnText}>{dash.label}</span>
        </button>
        {open === 'dash' ? (
          <div className={s.popover}>
            {DASHES.map((entry) => (
              <button
                key={entry.value}
                type="button"
                className={cx(s.listRow, selection.lineStyle === entry.value && s.listRowOn)}
                onClick={() => {
                  onStyle({ lineStyle: entry.value });
                  setOpen(null);
                }}
              >
                <span className={s.dashSample}>{entry.label}</span>
                <span>{entry.value}</span>
              </button>
            ))}
          </div>
        ) : null}
      </div>

      {selection.hasText ? (
        <>
          <span className={s.rule} aria-hidden="true" />
          <button type="button" className={s.btn} aria-label="Edit text" onClick={onEditText}>
            <span className={s.btnText}>T</span>
          </button>
        </>
      ) : null}

      <span className={s.rule} aria-hidden="true" />

      <button
        type="button"
        className={cx(s.btn, selection.locked && s.btnOn)}
        aria-label={selection.locked ? 'Unlock' : 'Lock'}
        aria-pressed={selection.locked}
        onClick={() => onStyle({ locked: !selection.locked })}
      >
        {drawToolIcon(selection.locked ? 'lock' : 'unlock', 16)}
      </button>
      <button type="button" className={s.btn} aria-label="Delete drawing" onClick={onDelete}>
        {drawToolIcon('trash', 16)}
      </button>
    </div>
  );
}
