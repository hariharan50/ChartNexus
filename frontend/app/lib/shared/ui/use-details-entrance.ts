import { useEffect } from 'react';

/**
 * Replays a `<details>` menu's entrance animation every time it opens.
 *
 * The menus animate in with `[open] > .panel { animation: cn-drop … }`, which
 * works the first time only. Chromium hides closed `<details>` content with
 * `content-visibility: hidden` and skips style recalculation inside it, so
 * closing never computes the "no animation" state — and reopening finds the
 * style unchanged and starts nothing. Resetting the panel's animation on the
 * `toggle` event is the one reliable way back in.
 *
 * One listener on the document (capture phase: `toggle` does not bubble)
 * covers every `<details>` in the app, present and future.
 */
export function useDetailsEntranceReplay(): void {
  useEffect(() => {
    function onToggle(event: Event) {
      const details = event.target;
      if (!(details instanceof HTMLDetailsElement) || !details.open) return;
      // The finished animation is gone from `getAnimations()`, so there is
      // nothing to rewind: clear it, flush style once, and let the stylesheet
      // start it fresh. Only the panel children, never the summary.
      const panels = [...details.children].filter(
        (el): el is HTMLElement =>
          el instanceof HTMLElement &&
          el.tagName !== 'SUMMARY' &&
          getComputedStyle(el).animationName !== 'none'
      );
      if (panels.length === 0) return;
      for (const el of panels) el.style.animation = 'none';
      void details.offsetWidth;
      for (const el of panels) el.style.animation = '';
    }
    document.addEventListener('toggle', onToggle, true);
    return () => document.removeEventListener('toggle', onToggle, true);
  }, []);
}
