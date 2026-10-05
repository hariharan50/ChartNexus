import SymbolAvatar from './SymbolAvatar';
import { cx } from './cx';
import s from './SymbolCell.module.css';

/**
 * A ticker with its company mark — the way every board in the terminal
 * identifies a row.
 *
 * The pairing was hand-copied into four boards before this existed, which is
 * the whole reason it does: the mark and the ticker have to share one flex
 * context with one gap, or the logo drifts off the text it labels.
 *
 * Deliberately *not* a wrapper that also prints the company name. The visible
 * text is the ticker, because that is what a trader scans and what fits a
 * dense column; the name is the hover label. Pages that want the name on
 * screen should lay it out themselves rather than widen this.
 *
 * The logo lookup is not here. `SymbolAvatar` owns the manifest check, the
 * generated-initials fallback for the ~19 F&O names with no usable mark, and
 * the `onError` guard — this only positions what it draws.
 */
interface Props {
  symbol: string;
  /** Company name. The hover label only; never rendered as text. */
  name?: string | null | undefined;
  /** Avatar edge in px. Omit for `SymbolAvatar`'s own default. */
  size?: number | undefined;
  /**
   * Extra class on the wrapper, for a page that owns the surrounding flex
   * context — a mirrored label, say — and needs to keep its own rules.
   */
  className?: string | undefined;
  /**
   * Extra class on the ticker. Pages style the ticker through their own
   * selectors (weight, colour, ellipsis width), so they need a hook that
   * survives the move into this component.
   */
  tickerClassName?: string | undefined;
}

export default function SymbolCell({ symbol, name, size, className, tickerClassName }: Props) {
  return (
    <span className={cx(s.cell, className)} title={name ?? undefined}>
      <SymbolAvatar symbol={symbol} {...(size === undefined ? {} : { size })} />
      <span className={cx(s.ticker, tickerClassName)}>{symbol}</span>
    </span>
  );
}
