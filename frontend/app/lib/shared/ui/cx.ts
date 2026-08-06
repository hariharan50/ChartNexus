/**
 * Joins class names, dropping anything falsy.
 *
 * Replaces Svelte's `class:active={cond}` directive:
 *   <summary class="nav-link" class:active={isActive}>
 *   <summary className={cx(s.navLink, isActive && s.active)}>
 *
 * Deliberately not a `clsx` dependency — six lines, and every call site in this
 * app passes a flat list of strings.
 */
export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ');
}
