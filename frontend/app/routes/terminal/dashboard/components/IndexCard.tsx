import { direction, formatPrice, formatSignedPercent } from '$shared/formatting/numbers';
import { cx } from '$shared/ui/cx';
import type { IndexQuote } from '../dashboard-data';
import s from './IndexCard.module.css';
import Pill from './Pill';

interface Props {
  quote: IndexQuote;
  selected?: boolean;
  onSelect?: (() => void) | undefined;
}

export default function IndexCard({ quote, selected = false, onSelect }: Props) {
  const dir = quote.changePercent !== undefined ? direction(quote.changePercent) : 'flat';
  const tone = dir === 'up' ? 'bullish' : dir === 'down' ? 'bearish' : 'neutral';

  return (
    <button
      type="button"
      className={cx(s.card, selected && s.selected, quote.pending && s.pending)}
      aria-pressed={selected}
      onClick={onSelect}
    >
      <span className={s.label}>{quote.label}</span>
      <span className={`${s.value} cn-numeric`}>
        {quote.pending ? '—' : formatPrice(quote.value)}
      </span>
      <span className={s.foot}>
        {quote.pending ? (
          <span className={s.await}>Awaiting market data</span>
        ) : quote.changePercent !== undefined ? (
          <Pill tone={tone}>{formatSignedPercent(quote.changePercent)}</Pill>
        ) : quote.tag ? (
          <Pill tone="accent">{quote.tag}</Pill>
        ) : null}
      </span>
    </button>
  );
}
