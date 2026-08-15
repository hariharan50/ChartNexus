/**
 * Inline line-icons for the landing page.
 *
 * Local to the marketing route rather than pulled from `$shared/ui/icons`: the
 * set here (feature tiles, social row) does not overlap the app's icon needs,
 * and inlining keeps the page self-contained with no new shared surface. All
 * are 24×24 stroke icons that inherit `currentColor`.
 */

export type GlyphName =
  | 'layers'
  | 'scale'
  | 'bars'
  | 'activity'
  | 'pulse'
  | 'shield'
  | 'code'
  | 'chat'
  | 'link'
  | 'mail'
  | 'clock'
  | 'database'
  | 'refresh'
  | 'ban'
  | 'wallet'
  | 'facebook'
  | 'instagram'
  | 'music'
  | 'phone';

function Svg({ children }: { children: React.ReactNode }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

const GLYPHS: Record<GlyphName, React.ReactNode> = {
  layers: (
    <>
      <path d="M12 3 2 8l10 5 10-5-10-5Z" />
      <path d="M2 16l10 5 10-5" />
      <path d="M2 12l10 5 10-5" />
    </>
  ),
  scale: (
    <>
      <path d="M12 3v18" />
      <path d="M5 7h14" />
      <path d="M5 7 2.5 13a3.5 3.5 0 0 0 5 0L5 7Z" />
      <path d="M19 7l-2.5 6a3.5 3.5 0 0 0 5 0L19 7Z" />
      <path d="M8 21h8" />
    </>
  ),
  bars: (
    <>
      <path d="M4 20V10" />
      <path d="M10 20V4" />
      <path d="M16 20v-7" />
      <path d="M22 20H2" />
    </>
  ),
  activity: <path d="M3 12h4l3 8 4-16 3 8h4" />,
  pulse: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M8 12h2l1.5 3 2-6 1.5 3H18" />
    </>
  ),
  shield: (
    <>
      <path d="M12 3 5 6v6c0 4 3 6.5 7 9 4-2.5 7-5 7-9V6l-7-3Z" />
      <path d="m9 12 2 2 4-4" />
    </>
  ),
  code: (
    <>
      <path d="m8 9-3 3 3 3" />
      <path d="m16 9 3 3-3 3" />
      <path d="m13 7-2 10" />
    </>
  ),
  chat: <path d="M21 12a8 8 0 0 1-11.3 7.3L3 21l1.7-6.7A8 8 0 1 1 21 12Z" />,
  link: (
    <>
      <path d="M10 13a5 5 0 0 0 7 0l2-2a5 5 0 0 0-7-7l-1 1" />
      <path d="M14 11a5 5 0 0 0-7 0l-2 2a5 5 0 0 0 7 7l1-1" />
    </>
  ),
  mail: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path d="m3 7 9 6 9-6" />
    </>
  ),
  clock: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3.5 2" />
    </>
  ),
  database: (
    <>
      <ellipse cx="12" cy="5.5" rx="8" ry="3" />
      <path d="M4 5.5v13c0 1.7 3.6 3 8 3s8-1.3 8-3v-13" />
      <path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3" />
    </>
  ),
  refresh: (
    <>
      <path d="M20 11a8 8 0 0 0-14-4.5L4 9" />
      <path d="M4 4v5h5" />
      <path d="M4 13a8 8 0 0 0 14 4.5L20 15" />
      <path d="M20 20v-5h-5" />
    </>
  ),
  ban: (
    <>
      <circle cx="12" cy="12" r="9" />
      <path d="M5.6 5.6 18.4 18.4" />
    </>
  ),
  wallet: (
    <>
      <rect x="3" y="6" width="18" height="13" rx="2.5" />
      <path d="M3 9h13a2 2 0 0 1 0 4H3" />
      <path d="M16.5 11h.01" />
    </>
  ),
  facebook: <path d="M14 8h2V5h-2a3 3 0 0 0-3 3v2H9v3h2v6h3v-6h2.2l.4-3H14V8.4c0-.3.2-.4.6-.4Z" />,
  instagram: (
    <>
      <rect x="4" y="4" width="16" height="16" rx="4.5" />
      <circle cx="12" cy="12" r="3.4" />
      <circle cx="16.4" cy="7.6" r="0.6" fill="currentColor" />
    </>
  ),
  music: (
    <>
      <path d="M9 18V6l9-2v10" />
      <circle cx="6.5" cy="18" r="2.5" />
      <circle cx="15.5" cy="16" r="2.5" />
    </>
  ),
  phone: (
    <path d="M6 3h3l1.5 4-2 1.5a12 12 0 0 0 5 5l1.5-2 4 1.5V21a2 2 0 0 1-2.2 2A16 16 0 0 1 4 6.2 2 2 0 0 1 6 4Z" />
  )
};

export function Icon({ name }: { name: GlyphName }) {
  return <Svg>{GLYPHS[name]}</Svg>;
}

export function IconCheck() {
  return (
    <Svg>
      <circle cx="12" cy="12" r="9" />
      <path d="m8.5 12 2.5 2.5 4.5-5" />
    </Svg>
  );
}

export function IconCross() {
  return (
    <Svg>
      <circle cx="12" cy="12" r="9" />
      <path d="M9 9l6 6" />
      <path d="M15 9l-6 6" />
    </Svg>
  );
}

export function IconClose() {
  return (
    <Svg>
      <path d="M6 6l12 12" />
      <path d="M18 6 6 18" />
    </Svg>
  );
}

export function IconLock() {
  return (
    <Svg>
      <rect x="5" y="11" width="14" height="9" rx="2" />
      <path d="M8 11V8a4 4 0 0 1 8 0v3" />
    </Svg>
  );
}
