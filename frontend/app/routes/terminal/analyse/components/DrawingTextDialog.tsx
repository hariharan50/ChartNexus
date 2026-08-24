import { useEffect, useRef, useState } from 'react';
import { cx } from '$shared/ui/cx';
import type { DrawTextStyle, TextRequest } from '$shared/charts/tv/drawings/useDrawings';
import s from './DrawingTextDialog.module.css';

const TITLES: Record<string, string> = {
  text: 'Text',
  callout: 'Callout',
  'price-label': 'Price label'
};

const SIZES = [10, 11, 12, 14, 16, 20, 24, 28, 32, 40];

/**
 * The note editor.
 *
 * Opens by itself the moment a text-bearing drawing is placed, because an empty
 * text box on a chart is invisible and the reader would have no way to discover
 * that it wants words. Cancelling out of one that is still empty removes it —
 * see `useDrawings`' `applyText`.
 */
interface Props {
  request: TextRequest;
  onSubmit: (id: string, value: DrawTextStyle) => void;
  onClose: () => void;
}

export default function DrawingTextDialog({ request, onSubmit, onClose }: Props) {
  const [value, setValue] = useState<DrawTextStyle>(request.style);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    setValue(request.style);
  }, [request]);

  useEffect(() => {
    const field = textareaRef.current;
    if (!field) return;
    field.focus();
    // Selected, not just focused: re-opening an existing note should be
    // type-over, which is what a reader who opened it to replace the text
    // expects and costs the one who wanted to append a single arrow key.
    field.select();
  }, [request]);

  const commit = () => {
    // `finally`, because this is a full-pane overlay. If `onSubmit` throws and
    // `onClose` is skipped, an invisible overlay swallows every subsequent
    // click on the chart and the chart looks dead.
    try {
      onSubmit(request.id, value);
    } finally {
      onClose();
    }
  };

  const patch = (part: Partial<DrawTextStyle>) => setValue((current) => ({ ...current, ...part }));

  return (
    <div
      className={s.overlay}
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
      role="presentation"
      // See `lw-host.ts`: keeps the text editor's clicks from reaching the chart's
      // pointer host underneath it.
      data-mc-chart-overlay=""
    >
      <div
        className={s.card}
        role="dialog"
        aria-modal="true"
        aria-label={TITLES[request.tool] ?? 'Text'}
      >
        <header className={s.header}>
          <h2 className={s.title}>{TITLES[request.tool] ?? 'Text'}</h2>
          <button type="button" className={s.close} aria-label="Close" onClick={onClose}>
            ×
          </button>
        </header>

        <div className={s.row}>
          <input
            type="color"
            className={s.color}
            aria-label="Text colour"
            value={value.color}
            onChange={(event) => patch({ color: event.target.value })}
          />
          <select
            className={s.select}
            aria-label="Font size"
            value={value.fontSize}
            onChange={(event) => patch({ fontSize: Number(event.target.value) })}
          >
            {SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
          <button
            type="button"
            className={cx(s.toggle, s.bold, value.bold && s.toggleOn)}
            aria-pressed={value.bold}
            aria-label="Bold"
            onClick={() => patch({ bold: !value.bold })}
          >
            B
          </button>
          <button
            type="button"
            className={cx(s.toggle, s.italic, value.italic && s.toggleOn)}
            aria-pressed={value.italic}
            aria-label="Italic"
            onClick={() => patch({ italic: !value.italic })}
          >
            I
          </button>
        </div>

        <textarea
          ref={textareaRef}
          className={s.textarea}
          rows={4}
          placeholder="Type a note. Shift+Enter for a new line."
          value={value.text}
          onChange={(event) => patch({ text: event.target.value })}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault();
              commit();
            }
            if (event.key === 'Escape') {
              event.preventDefault();
              onClose();
            }
          }}
        />

        <div className={s.row}>
          <label className={s.check}>
            <input
              type="checkbox"
              checked={value.background}
              onChange={(event) => patch({ background: event.target.checked })}
            />
            Background
          </label>
          {/* Stays visible but disabled while the toggle is off, so its value
              survives being switched off and back on. */}
          <input
            type="color"
            className={cx(s.color, !value.background && s.dim)}
            aria-label="Background colour"
            disabled={!value.background}
            value={value.backgroundColor}
            onChange={(event) => patch({ backgroundColor: event.target.value })}
          />
        </div>

        <div className={s.row}>
          <label className={s.check}>
            <input
              type="checkbox"
              checked={value.border}
              onChange={(event) => patch({ border: event.target.checked })}
            />
            Border
          </label>
          <input
            type="color"
            className={cx(s.color, !value.border && s.dim)}
            aria-label="Border colour"
            disabled={!value.border}
            value={value.borderColor}
            onChange={(event) => patch({ borderColor: event.target.value })}
          />
        </div>

        <label className={s.check}>
          <input
            type="checkbox"
            checked={value.wrap}
            onChange={(event) => patch({ wrap: event.target.checked })}
          />
          Text wrap
        </label>

        <footer className={s.footer}>
          <button type="button" className={s.secondary} onClick={onClose}>
            Cancel
          </button>
          <button type="button" className={s.primary} onClick={commit}>
            Ok
          </button>
        </footer>
      </div>
    </div>
  );
}
