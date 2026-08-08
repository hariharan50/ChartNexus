import { useCallback, useEffect, useRef, useState } from 'react';
import { useLocation } from 'react-router';

/**
 * Open/close machinery for the nav drawer, built on a native `<dialog>`.
 *
 * `showModal()` is doing real work here that would otherwise be hand-rolled: it
 * traps focus inside the panel, stacks it in the top layer so it clears the
 * sticky header without any z-index arithmetic, marks the rest of the document
 * inert, and gives Escape for free. The terminal's `<details>` dropdowns are
 * fine for a small menu where escaping focus is survivable; a full-height panel
 * covering the page is not.
 */
export function useDrawer() {
  const [open, setOpen] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const location = useLocation();

  const close = useCallback(() => setOpen(false), []);

  // Drive the dialog from state rather than calling showModal() in the click
  // handler: the element renders closed on the server and on first client
  // render, so hydration matches, and the effect opens it afterwards.
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    if (open && !dialog.open) dialog.showModal();
    else if (!open && dialog.open) dialog.close();
  }, [open]);

  // Escape and the close button both fire the native `close` event. Syncing
  // state from the event rather than only from our own handler is what stops
  // React's idea of `open` drifting from the DOM's.
  //
  // The backdrop click is wired here too rather than as an `onClick` in the
  // JSX: a `<dialog>` is not an interactive element, so a click handler on it
  // is a jsx-a11y violation — correctly, since a mouse-only dismissal needs a
  // keyboard equivalent. Escape and the close button are that equivalent, and
  // attaching natively keeps every dialog behaviour in this one hook.
  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;

    const onClose = () => setOpen(false);
    // A click landing on the dialog itself is a backdrop hit — the panel and
    // everything in it are children, so they never match.
    const onClick = (event: MouseEvent) => {
      if (event.target === dialog) setOpen(false);
    };

    dialog.addEventListener('close', onClose);
    dialog.addEventListener('click', onClick);
    return () => {
      dialog.removeEventListener('close', onClose);
      dialog.removeEventListener('click', onClick);
    };
  }, []);

  // showModal() blocks background scroll in Chrome but not everywhere, so lock
  // it explicitly and restore whatever was there before.
  useEffect(() => {
    if (!open) return;

    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.body.style.overflow = previous;
    };
  }, [open]);

  // Return focus to the hamburger. `<dialog>` restores focus itself in modern
  // browsers, but only down the `close()` path — doing it here covers the rest.
  // Guarded on having been opened at least once: without it the effect's first
  // run, on mount, would pull focus to the hamburger on page load.
  const opened = useRef(false);
  useEffect(() => {
    if (open) {
      opened.current = true;
      return;
    }
    if (opened.current) triggerRef.current?.focus({ preventScroll: true });
  }, [open]);

  // Close after a navigation, the same way the terminal header closes its open
  // menus (routes/terminal/layout.tsx). A drawer still covering the page you
  // just navigated to is the most obvious version of this bug.
  useEffect(() => {
    setOpen(false);
  }, [location.pathname]);

  return { open, setOpen, close, dialogRef, triggerRef };
}
