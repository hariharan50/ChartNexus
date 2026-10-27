import type { ExpiryKind, ExpiryUrgency } from '$contexts/market-data/expiry-calendar';
import { cx } from '$shared/ui/cx';
import s from './ExpiryTriangle.module.css';

interface Props {
  kind: ExpiryKind;
  urgency: ExpiryUrgency;
  /** Smaller variant for the spot card's corner. */
  compact?: boolean;
}

/**
 * The expiry marker glyph: a triangle whose colour names the contract and
 * whose fill names the urgency.
 *
 * **Colour carries type, not severity.** Red is the weekly, amber the monthly,
 * and that mapping never changes with how close the date is — a reader who has
 * learned "red means the weekly" must not find red meaning "imminent" on a
 * different row of the same card.
 *
 * Urgency rides on fill instead: outline when the date is a few days out, solid
 * once it is tomorrow, solid and pulsing on the day itself. Shape and fill are
 * doing the work colour cannot, which is also what keeps the card readable for
 * a reader who cannot separate red from amber — every triangle sits beside the
 * word `Weekly` or `Monthly`, and this element is `aria-hidden` precisely
 * because that text is the real label.
 *
 * `both` is a monthly expiry that is also its week's weekly. It draws both
 * triangles, overlapped, rather than picking a side.
 */
export default function ExpiryTriangle({ kind, urgency, compact = false }: Props) {
  if (kind === 'both') {
    return (
      <span className={cx(s.stack, compact && s.compact)} aria-hidden="true">
        <Glyph kind="monthly" urgency={urgency} />
        <Glyph kind="weekly" urgency={urgency} />
      </span>
    );
  }

  return (
    <span className={cx(s.single, compact && s.compact)} aria-hidden="true">
      <Glyph kind={kind} urgency={urgency} />
    </span>
  );
}

function Glyph({ kind, urgency }: { kind: 'weekly' | 'monthly'; urgency: ExpiryUrgency }) {
  // `today` and `tomorrow` fill the triangle; the rest leave it hollow. A
  // hollow shape reads as "noted", a filled one as "now", which is the
  // distinction the card is actually trying to draw.
  const filled = urgency === 'today' || urgency === 'tomorrow';

  return (
    <svg
      className={cx(s.glyph, s[kind], filled && s.filled, urgency === 'today' && s.live)}
      xmlns="http://www.w3.org/2000/svg"
      width="20"
      height="20"
      viewBox="0 0 24 24"
      fill={filled ? 'currentColor' : 'none'}
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M12 4 21.5 20.5H2.5Z" />
    </svg>
  );
}
