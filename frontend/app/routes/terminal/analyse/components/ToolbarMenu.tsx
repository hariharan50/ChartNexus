import { useLayoutEffect, useRef, useState, type ReactNode, type RefObject } from 'react';
import { createPortal } from 'react-dom';
import { cx } from '$shared/ui/cx';
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
/**
 * `.menu`'s `min-width: 10rem`, in px — the assumed width for the very first
 * measurement, before the panel exists to be measured. Panels are free to be
 * wider (the Indicators one is), which is why every measurement after that one
 * reads the real width off the rendered element instead.
 */
const MENU_MIN_WIDTH = 160;

interface Props {
  anchorRef: RefObject<HTMLElement | null>;
  open: boolean;
  /** Extra class on the panel, for a menu that needs to be wider than the default. */
  className?: string | undefined;
  children: ReactNode;
}

export default function ToolbarMenu({ anchorRef, open, className, children }: Props) {
  const [rect, setRect] = useState<{ top: number; left: number } | null>(null);
  const panel = useRef<HTMLDivElement>(null);
  // The panel renders only once `rect` exists, so this is also "the panel is in
  // the DOM and can be measured".
  const mounted = rect !== null;

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
      // Measured from the panel itself once it exists, since panels differ in
      // width and a clamp against the wrong one is no clamp at all. The pass
      // that mounts it runs against the minimum, and the layout effect below
      // immediately re-runs this with the real number.
      const width = panel.current?.getBoundingClientRect().width ?? MENU_MIN_WIDTH;
      const left = Math.max(4, Math.min(r.left, window.innerWidth - width - 4));
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
    // `mounted` is listed so this runs a second time the moment the panel is on
    // screen, to re-clamp against its true width. It settles there: `update`
    // returns the identical state object when nothing moved, and this dependency
    // is a boolean that has already finished changing.
  }, [open, anchorRef, mounted]);

  if (!open || !rect) return null;

  return createPortal(
    <div
      ref={panel}
      className={cx(s.menu, className)}
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
