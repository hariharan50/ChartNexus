import type { HeadlineCard } from '$contexts/pre-market/types';
import { cx } from '$shared/ui/cx';
import { GAP_LABELS, fmtAtr, fmtChange, fmtLevel, fmtPercent, gapTone, tone } from '../pms-data';
import s from './HeadlineCards.module.css';

interface Props {
  cards: HeadlineCard[];
  focus: string;
  onFocus: (symbol: string) => void;
}

/**
 * NIFTY, BANK NIFTY and SENSEX across the top, and the focus picker.
 *
 * Two gaps per card, kept apart on purpose. The **gap** is what the index
 * actually opened at against its previous close — it does not exist before
 * 09:15, and is never back-filled from GIFT, because a quote is not a print.
 * The **implied gap** is what GIFT NIFTY is quoting, and only NIFTY has one:
 * the other two have no overnight contract, and borrowing NIFTY's would invent
 * a number the market never made.
 *
 * The ATR multiple is shown beside the percentage because sixty points is a
 * shrug on a wide-range index and an event on a quiet one, and only the
 * multiple carries that across three instruments of different sizes.
 */
export default function HeadlineCards({ cards, focus, onFocus }: Props) {
  return (
    <div className={s.row} role="group" aria-label="Headline indices">
      {cards.map((card) => {
        const selected = card.symbol === focus;
        const gap = card.gap ?? card.implied_gap;
        const quoted = card.gap === null && card.implied_gap !== null;

        return (
          <button
            type="button"
            key={card.symbol}
            className={cx(s.card, selected && s.selected)}
            aria-pressed={selected}
            onClick={() => onFocus(card.symbol)}
          >
            <span className={s.label}>{card.label}</span>
            <span className={cx(s.price, 'cn-numeric')}>{fmtLevel(card.price)}</span>

            <span className={cx(s.change, 'cn-numeric', s[tone(card.change_percent) ?? 'flat'])}>
              {fmtChange(card.change)} ({fmtPercent(card.change_percent)})
            </span>

            {gap ? (
              <span className={s.gapRow}>
                <span className={cx(s.gapTag, s[gapTone(gap.bucket) ?? 'flat'])}>
                  {GAP_LABELS[gap.bucket]}
                </span>
                <span className={cx(s.gapFigure, 'cn-numeric')}>
                  {fmtPercent(gap.percent)}
                  {gap.basis === 'atr' ? ` · ${fmtAtr(gap.atr_multiple)} ATR` : ''}
                </span>
              </span>
            ) : (
              <span className={s.gapRow}>
                <span className={s.pending}>No open yet</span>
              </span>
            )}

            {/* Naming which of the two is on screen. Before 09:15 this is a
                contract's opinion; after it, an observed print. Rendering them
                identically would let a quote be read as a fact. */}
            <span className={s.basis}>
              {quoted ? 'GIFT-implied' : card.gap ? 'Opened at' : 'Awaiting the open'}
            </span>

            {!card.breadth_tracked ? (
              <span className={s.untracked}>Breadth not tracked</span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
