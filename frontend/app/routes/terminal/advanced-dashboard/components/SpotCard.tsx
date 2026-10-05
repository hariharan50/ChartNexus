import type { IndexQuote } from '$contexts/market-data/view-models';
import { direction, formatPrice, formatSignedPercent } from '$shared/formatting/numbers';
import { cx } from '$shared/ui/cx';
import s from './SpotCard.module.css';

interface Props {
  quote: IndexQuote;
  selected?: boolean;
  onSelect?: (() => void) | undefined;
}

export default function SpotCard({ quote, selected = false, onSelect }: Props) {
  const dir = quote.changePercent !== undefined ? direction(quote.changePercent) : 'flat';

  return (
    <button
      type="button"
      className={cx(s.card, selected && s.selected, quote.pending && s.pending)}
      aria-pressed={selected}
      onClick={onSelect}
    >
      <span className={s.label}>{quote.label}</span>
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
