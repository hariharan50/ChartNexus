import type { ReactNode } from 'react';
import s from './SettingsIcon.module.css';

interface Props {
  name: string;
}

const GLYPHS: Record<string, ReactNode> = {
  book: (
    <>
      <path d="M4 5.5A1.5 1.5 0 0 1 5.5 4H12v15H5.5A1.5 1.5 0 0 0 4 20.5Z" />
      <path d="M20 5.5A1.5 1.5 0 0 0 18.5 4H12v15h6.5A1.5 1.5 0 0 1 20 20.5Z" />
    </>
  ),
  lifebuoy: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="3.5" />
      <path d="M14.5 9.5 18 6M9.5 9.5 6 6M14.5 14.5 18 18M9.5 14.5 6 18" />
    </>
  ),
  bug: (
    <>
      <rect x="8" y="8" width="8" height="10" rx="4" />
      <path d="M9 6a3 3 0 0 1 6 0M4 11h3M17 11h3M4 16h3M17 16h3M12 8v10" />
    </>
  ),
  users: (
    <>
      <circle cx="9" cy="8" r="3" />
      <path d="M3.5 19a5.5 5.5 0 0 1 11 0" />
      <path d="M16 5.5a3 3 0 0 1 0 5.8M17 19a5.5 5.5 0 0 0-2-4.3" />
    </>
  ),
  chevron: <path d="m9 6 6 6-6 6" />,
  user: (
    <>
      <circle cx="12" cy="8.5" r="3.5" />
      <path d="M4.5 20a7.5 7.5 0 0 1 15 0" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3.5 5 6v5.5c0 4.2 2.9 7.4 7 8.5 4.1-1.1 7-4.3 7-8.5V6Z" />
      <path d="m9.25 11.75 1.9 1.9 3.6-3.9" />
    </>
  ),
  bell: (
    <>
      <path d="M6 10.5a6 6 0 0 1 12 0v3.3c0 .7.2 1.4.7 2l.6.7H4.7l.6-.7c.5-.6.7-1.3.7-2Z" />
      <path d="M10 19.5a2 2 0 0 0 4 0" />
    </>
  ),
  link: (
    <>
      <path d="M10 14a4.5 4.5 0 0 1 0-6.4l2.2-2.2a4.5 4.5 0 1 1 6.4 6.4l-1.3 1.3" />
      <path d="M14 10a4.5 4.5 0 0 1 0 6.4l-2.2 2.2a4.5 4.5 0 1 1-6.4-6.4l1.3-1.3" />
    </>
  ),
  sliders: (
    <>
      <path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h13M21 18h-1" />
      <circle cx="13" cy="6" r="2" />
      <circle cx="7" cy="12" r="2" />
      <circle cx="19" cy="18" r="2" />
    </>
  ),
  card: (
    <>
      <rect x="3.5" y="6" width="17" height="12" rx="2" />
      <path d="M3.5 10.5h17M7 14.5h4" />
    </>
  )
};

export default function SettingsIcon({ name }: Props) {
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
