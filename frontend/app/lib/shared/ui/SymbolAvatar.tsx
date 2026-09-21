import s from './SymbolAvatar.module.css';

/**
 * A company mark for a ticker.
 *
 * Generated, not fetched. Real logos would mean a third-party image request per
 * row — two hundred of them on this board — plus a licensing question and a
 * broken-image state to design. Initials in a stable colour identify a row just
 * as well when you are scanning for one you already know.
 *
 * The colour is derived from the ticker, so a symbol looks the same everywhere
 * it appears and the eye can use it as a handle.
 */
interface Props {
  symbol: string;
  size?: number;
}

/** Hues spaced around the wheel, skipping the red/green band so an avatar is
 *  never mistaken for an up or down signal. */
const HUES = [212, 258, 284, 318, 34, 46, 190, 168];

export default function SymbolAvatar({ symbol, size = 22 }: Props) {
  const hue = HUES[hash(symbol) % HUES.length]!;
  const initials = symbol
    .replace(/[^A-Za-z0-9]/g, '')
    .slice(0, 2)
    .toUpperCase();

  return (
    <span
      className={s.avatar}
      aria-hidden="true"
      style={{
        width: size,
        height: size,
        // Lightness is fixed rather than themed: these sit on both light and
        // dark surfaces and must stay legible against either.
        background: `hsl(${hue} 62% 42%)`,
        fontSize: Math.round(size * 0.42)
      }}
    >
      {initials}
    </span>
  );
}

function hash(value: string): number {
  let total = 0;
  for (let i = 0; i < value.length; i += 1) total = (total * 31 + value.charCodeAt(i)) >>> 0;
  return total;
}
