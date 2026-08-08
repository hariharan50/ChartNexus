import { useCallback, useEffect, useRef } from 'react';
import { useLocation } from 'react-router';

/**
 * Outside-click, Escape and close-on-navigate for native `<details>` menus.
 *
 * `<details>` gives a disclosure that works without JavaScript, but on its own
 * it does none of the three things a *menu* has to do: it stays open when you
 * click elsewhere, it ignores Escape, and it survives a navigation. This adds
 * exactly those, and nothing else.
 *
 * The same logic runs the terminal header (`routes/terminal/layout.tsx`).
 * Copied rather than imported: a marketing page reaching into the terminal's
 * layout module for a helper would tie the two together for no reason, and the
 * shape is fifteen lines.
 */
export function useMenuDismiss<T extends HTMLElement>() {
  const root = useRef<T>(null);

  const closeAll = useCallback((except?: EventTarget | null) => {
    const host = root.current;
    if (!host) return;

    for (const menu of host.querySelectorAll<HTMLDetailsElement>('details[open]')) {
      // A click inside one menu closes its siblings but not itself, so moving
      // between menus does not need two clicks.
      if (except instanceof Node && menu.contains(except)) continue;
      menu.open = false;
    }
  }, []);

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      const host = root.current;
      if (!host) return;
      const target = event.target;
      if (target instanceof Node && host.contains(target)) closeAll(target);
      else closeAll();
    };

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') closeAll();
    };

    document.addEventListener('pointerdown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('pointerdown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [closeAll]);

  const location = useLocation();
  useEffect(() => {
    closeAll();
  }, [location.pathname, closeAll]);

  return root;
}
