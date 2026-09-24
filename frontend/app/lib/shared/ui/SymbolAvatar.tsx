import { useState } from 'react';
import { cx } from './cx';
import MANIFEST from './logo-manifest.json';
import s from './SymbolAvatar.module.css';

/**
 * A company mark for a ticker.
 *
 * **The real logo where we have one, generated initials where we do not.**
 *
 * The logos are served from our own origin, out of `public/logos/`, fetched
 * once by `scripts/fetch-logos.mjs` and committed. That is the whole design:
 * asking a logo service per row would be two hundred third-party requests on a
 * board that polls every fifteen seconds, it would tell that service which
 * stocks every viewer is watching, and it would break the moment the service
 * did or the developer went offline.
 *
 * About forty of the F&O names have no usable mark — a company whose site
 * serves no icon, or one whose icon turned out to be a shared CDN placeholder,
 * which the fetcher rejects rather than ship as a logo. Those keep the
 * generated initials this component has always drawn, which is why that code
 * is still here rather than deleted.
 *
 * The manifest is consulted *before* rendering rather than relying on the
 * image failing: a miss would otherwise cost a 404 per row, and the reader
 * would see the broken-image frame for one paint before the fallback swapped
 * in. `onError` stays as a second line of defence for a file that is listed
 * but unreadable.
 */
interface Props {
  symbol: string;
  size?: number;
}

/** Hues spaced around the wheel, skipping the red/green band so an avatar is
 *  never mistaken for an up or down signal. */
const HUES = [212, 258, 284, 318, 34, 46, 190, 168];

/**
 * Symbol to file extension. Not a plain set: the server sets `Content-Type`
 * from the extension, so an SVG mark addressed as `.png` is a broken image.
 */
const LOGOS = MANIFEST as Record<string, string>;

export default function SymbolAvatar({ symbol, size = 22 }: Props) {
  const [failed, setFailed] = useState(false);
  const key = symbol.trim().toUpperCase();

  const ext = LOGOS[key];

  if (ext && !failed) {
    return (
      <img
        className={cx(s.avatar, s.logo)}
        src={`/logos/${encodeURIComponent(key)}.${ext}`}
        alt=""
        aria-hidden="true"
        width={size}
        height={size}
        loading="lazy"
        decoding="async"
        style={{ width: size, height: size }}
        onError={() => setFailed(true)}
      />
    );
  }

  const hue = HUES[hash(key) % HUES.length]!;
  const initials = key
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
