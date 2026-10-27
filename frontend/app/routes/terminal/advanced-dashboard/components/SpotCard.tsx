import {
  type ExpiryMarker,
  countdownLabel,
  expiryDateLabel,
  kindLabel
} from '$contexts/market-data/expiry-calendar';
import type { IndexQuote } from '$contexts/market-data/view-models';
import { direction, formatPrice, formatSignedPercent } from '$shared/formatting/numbers';
import { cx } from '$shared/ui/cx';
import ExpiryTriangle from './ExpiryTriangle';
import s from './SpotCard.module.css';

interface Props {
  quote: IndexQuote;
  selected?: boolean;
  onSelect?: (() => void) | undefined;
  /** The index's nearest expiry, marked in the card's corner. The Expiry Radar
      section below carries the full calendar; this is only so the signal is
      reachable without scrolling past the futures and metrics rows. */
  expiry?: ExpiryMarker | undefined;
}

export default function SpotCard({ quote, selected = false, onSelect, expiry }: Props) {
  const dir = quote.changePercent !== undefined ? direction(quote.changePercent) : 'flat';

  return (
    <button
      type="button"
      className={cx(s.card, selected && s.selected, quote.pending && s.pending)}
      aria-pressed={selected}
      onClick={onSelect}
    >
      <span className={s.label}>{quote.label}</span>

      {/* Positioned rather than placed in flow so it cannot shift the price,
          which is what the card is actually for. The title is the whole label
          for a sighted hover; the visually-hidden span is what a screen reader
          reads, since the triangle itself is aria-hidden. */}
      {expiry ? (
        <span
          className={s.expiry}
          title={`${kindLabel(expiry.kind)} expiry ${expiryDateLabel(expiry.date)} — ${countdownLabel(expiry.daysAway).toLowerCase()}`}
        >
          <ExpiryTriangle kind={expiry.kind} urgency={expiry.urgency} compact />
          <span className="cn-visually-hidden">
            {kindLabel(expiry.kind)} expiry {expiryDateLabel(expiry.date)},{' '}
            {countdownLabel(expiry.daysAway).toLowerCase()}
          </span>
        </span>
      ) : null}
      <span className={cx(s.value, 'cn-numeric')}>
        {quote.pending ? '—' : formatPrice(quote.value)}
      </span>
      <span className={s.foot}>
        {quote.pending ? (
          <span className={s.await}>Awaiting market data</span>
        ) : quote.changePercent !== undefined ? (
          <span className={cx(s.pill, s[dir])}>{formatSignedPercent(quote.changePercent)}</span>
        ) : null}
      </span>
      <span className={cx(s.accent, s[dir])} aria-hidden="true" />
    </button>
  );
}
