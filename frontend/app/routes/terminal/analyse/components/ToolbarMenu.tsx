import { useLayoutEffect, useState, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import s from './TopToolbar.module.css';

/**
 * A toolbar dropdown's panel, portaled to `document.body`.
 *
 * `TopToolbar`'s button strip scrolls horizontally on narrow screens
 * (`.bar { overflow-x: auto }`), and per the CSS spec setting one overflow axis
 * to anything but `visible` computes the *other* axis to `auto` too — so a
 * panel positioned `absolute` inside that bar was clipped by its 48px height
 * the instant it dropped below it. Portaling out from under `.bar` altogether
 * sidesteps that regardless of the bar's own overflow, rather than trying to
 * keep the bar's scroll and the panel's clipping in permanent agreement.
 *
 * Positioned in viewport (`fixed`) coordinates read from the trigger on open,
 * not CSS anchoring, since the trigger can sit inside the scrolled strip.
 */
/** `.menu`'s `min-width: 10rem`, in px — enough to keep the panel on screen. */
const MENU_WIDTH = 160;

interface Props {
  anchorRef: RefObject<HTMLElement | null>;
  open: boolean;
  children: ReactNode;
}

export default function ToolbarMenu({ anchorRef, open, children }: Props) {
  const [rect, setRect] = useState<{ top: number; left: number } | null>(null);

  useLayoutEffect(() => {
    if (!open) {
      setRect(null);
      return;
    }
    const anchor = anchorRef.current;
    if (!anchor) return;

    function update() {
      const r = anchor!.getBoundingClientRect();
      // Kept on screen: a trigger near the right edge would otherwise hang a
      // fixed panel off the viewport with nothing to scroll it back into view.
      const left = Math.max(4, Math.min(r.left, window.innerWidth - MENU_WIDTH - 4));
      setRect((current) =>
        current && current.top === r.bottom + 6 && current.left === left
          ? current
          : { top: r.bottom + 6, left }
      );
    }
    update();

    // Coalesced to one measurement per frame. This listens in the capture
    // phase, so it hears *every* scrollable ancestor on the page, and a
    // `getBoundingClientRect` per event on a momentum scroll is a layout
    // flush per event.
    let frame = 0;
    function schedule() {
      if (frame) return;
      frame = window.requestAnimationFrame(() => {
        frame = 0;
        update();
      });
    }

    // The bar's own horizontal scroll, or a window resize, moves the trigger
    // out from under a panel that only read its position once on open.
    window.addEventListener('scroll', schedule, true);
    window.addEventListener('resize', schedule);
    return () => {
      if (frame) window.cancelAnimationFrame(frame);
      window.removeEventListener('scroll', schedule, true);
      window.removeEventListener('resize', schedule);
    };
  }, [open, anchorRef]);

  if (!open || !rect) return null;

  return createPortal(
    <div
      className={s.menu}
      role="menu"
      // Marks this subtree as "inside the toolbar" for the outside-click
      // detector in `TopToolbar`, which otherwise only knows about `.bar` and
      // would see every click in a portaled panel as outside it.
      data-toolbar-menu=""
      style={{ position: 'fixed', top: rect.top, left: rect.left }}
    >
      {children}
    </div>,
    document.body
  );
}
