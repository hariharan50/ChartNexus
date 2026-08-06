import type { ReactNode } from 'react';
import s from './OptionsLabIcon.module.css';

// Small line glyphs for the Options Lab mega-menu. One lookup keeps the whole
// set in a single file rather than scattering ~18 tiny icon components.
interface Props {
  name: string;
}

const GLYPHS: Record<string, ReactNode> = {
  layers: (
    <>
      <path d="M12 3 21 8l-9 5-9-5 9-5Z" />
      <path d="M3 13l9 5 9-5" />
    </>
  ),
  bars: <path d="M5 20V11M12 20V5M19 20v-6" />,
  scale: (
    <>
      <path d="M12 4v16M6 8h12" />
      <circle cx="6" cy="8" r="1.4" />
      <circle cx="18" cy="8" r="1.4" />
    </>
  ),
  target: (
    <>
      <circle cx="12" cy="12" r="8" />
      <circle cx="12" cy="12" r="3.5" />
    </>
  ),
  activity: <path d="M3 12h3l3 7 4-15 3 8h5" />,
  diff: <path d="M8 7 4 11l4 4M16 7l4 4-4 4M4 11h16" />,
  trend: (
    <>
      <path d="M4 16l5-5 3 3 8-8" />
      <path d="M20 6h-4M20 6v4" />
    </>
  ),
  strategy: (
    <>
      <circle cx="6" cy="7" r="2" />
      <circle cx="6" cy="17" r="2" />
      <circle cx="18" cy="12" r="2" />
      <path d="M8 8l8 3M8 16l8-3" />
    </>
  ),
  sparkle: <path d="M12 3l1.7 5.3L19 10l-5.3 1.7L12 17l-1.7-5.3L5 10l5.3-1.7Z" />,
  sigma: <path d="M17 5H7l6 7-6 7h10" />,
  flow: <path d="M4 9h11l-3-3M4 9l3 3M20 15H9l3 3M20 15l-3-3" />,
  straddle: (
    <>
      <path d="M12 4v6M12 10 6 19M12 10l6 9" />
      <circle cx="12" cy="4" r="1.3" />
    </>
  ),
  timer: (
    <>
      <circle cx="12" cy="13" r="7" />
      <path d="M12 13V9M10 3h4" />
    </>
  ),
  grid: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="1.5" />
      <path d="M4 12h16M12 4v16" />
    </>
  ),
  percent: (
    <>
      <path d="M6 18 18 6" />
      <circle cx="7.5" cy="7.5" r="2" />
      <circle cx="16.5" cy="16.5" r="2" />
    </>
  ),
  crossover: <path d="M4 6l16 12M4 18l16-12" />,
  alert: (
    <>
      <path d="M6 16h12l-1.5-2.5V10a4.5 4.5 0 0 0-9 0v3.5Z" />
      <path d="M10.5 19a1.5 1.5 0 0 0 3 0" />
    </>
  ),
  eye: (
    <>
      <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6S2 12 2 12Z" />
      <circle cx="12" cy="12" r="2.5" />
    </>
  ),
  gauge: (
    <>
      <path d="M4 15a8 8 0 1 1 16 0" />
      <path d="M12 15l4-5" />
      <path d="M12 15v.01" />
    </>
  ),
  cycle: (
    <>
      <path d="M12 3a9 9 0 1 0 9 9" />
      <path d="M12 3v6l5-2.5Z" />
    </>
  )
};

export default function OptionsLabIcon({ name }: Props) {
  return (
    <svg
      className={s.glyph}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {GLYPHS[name] ?? <circle cx="12" cy="12" r="8" />}
    </svg>
  );
}
