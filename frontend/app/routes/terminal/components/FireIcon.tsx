/**
 * The flat three-tone flame, as vector rather than the 🔥 emoji.
 *
 * An emoji would be one character, but it is drawn by whichever colour-emoji
 * font the reader's OS ships — Segoe UI Emoji here, Apple Color Emoji on a Mac,
 * Noto on Linux — so the mark changes shape between machines and is missing
 * outright where no emoji font is installed. That is the same class of bug as
 * the JetBrains Mono fallback on Stock Watch: a glyph the app does not ship.
 * Drawn here, it is identical everywhere and stays crisp at any size.
 *
 * Deliberately not `currentColor`: this is a status mark whose whole job is to
 * be the one warm thing in a cool menu, so the three tones are fixed and it
 * reads the same in both themes.
 */
export default function FireIcon({ className }: { className?: string | undefined }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" aria-hidden="true">
      {/* Outer flame, with the tongue that curls back in on the right. */}
      <path
        d="M11.5 1.5c.7 3.1-.4 5.4-2.1 7.4-2 2.3-4.6 4.2-4.6 7.3 0 3.8 3.2 6.6 7.2 6.6s7.2-2.8 7.2-6.6c0-2.2-.8-3.9-2-5.6.2 1.3.1 2.5-.7 3.2-.7.6-1.8.4-2.3-.4-.6-1-.2-2.2-.2-3.4 0-3.5-.8-6.6-2.5-8.5Z"
        fill="#F8481C"
      />
      {/* Mid flame. */}
      <path
        d="M12 6.6c1 3-.3 4.7-1.6 6.3-1.1 1.3-2 2.2-2 3.7 0 2.5 1.6 4.3 3.7 4.3s3.7-1.8 3.7-4.3c0-2-1-3.3-2-4.7-.8-1.1-1.5-3-1.8-5.3Z"
        fill="#FD9A2B"
      />
      {/* Core. */}
      <path
        d="M12.2 12.2c.4 1.9-.5 2.8-1.2 3.7-.5.7-.8 1.3-.8 2.1 0 1.4.9 2.4 2 2.4s2-1 2-2.4c0-1.1-.6-1.8-1.2-2.7-.4-.7-.7-1.9-.8-3.1Z"
        fill="#FFE9A8"
      />
    </svg>
  );
}
