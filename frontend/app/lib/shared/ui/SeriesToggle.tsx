import { cx } from './cx';
import IconEye from './icons/IconEye';
import IconEyeOff from './icons/IconEyeOff';
import s from './SeriesToggle.module.css';

/**
 * A legend chip that shows or hides its series.
 *
 * The chart's own legend lives inside the canvas: unreachable by keyboard,
 * invisible to a screen reader, and styled by ECharts rather than by the design
 * tokens. This is the legend the reader actually uses — a real button, with an
 * eye that follows the state and the series' own colour as the swatch.
 *
 * Lifted out of MultiStrike, which is where the pattern was proven, so every
 * chart with switchable series behaves identically.
 */
interface Props {
  label: string;
  /** The series' colour. Omit for a `dashed` chip, which uses the text colour. */
  color?: string | undefined;
  /** Draw a dotted rule instead of a filled swatch — for a reference line. */
  dashed?: boolean | undefined;
  on: boolean;
  onToggle: () => void;
  /** Why this one cannot be switched off right now, e.g. the last line left. */
  disabledReason?: string | undefined;
}

export default function SeriesToggle({
  label,
  color,
  dashed,
  on,
  onToggle,
  disabledReason
}: Props) {
  return (
    <button
      type="button"
      className={cx(s.entry, !on && s.off)}
      aria-pressed={on}
      title={disabledReason}
      onClick={onToggle}
    >
      <span className={s.eye} aria-hidden="true">
        {on ? <IconEye /> : <IconEyeOff />}
      </span>
      {dashed ? (
        <span className={s.dash} aria-hidden="true" />
      ) : (
        <span className={s.swatch} style={{ background: color }} aria-hidden="true" />
      )}
      <span className={s.label}>{label}</span>
    </button>
  );
}
