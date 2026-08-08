import { Link } from 'react-router';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import IconClose from '$shared/ui/icons/IconClose';
import { NAV_LINKS, NAV_TOOLS } from '../copy';
import s from './NavDrawer.module.css';

interface Props {
  id: string;
  onClose: () => void;
  dialogRef: React.RefObject<HTMLDialogElement | null>;
}

/**
 * Opening, closing, Escape, the backdrop click, scroll lock and focus return
 * all live in `use-drawer`. This component is only the contents.
 */
export default function NavDrawer({ id, onClose, dialogRef }: Props) {
  return (
    <dialog id={id} ref={dialogRef} className={s.drawer} aria-label="Site navigation">
      <div className={s.panel}>
        <div className={s.head}>
          <span className={s.headLabel}>Menu</span>
          <button type="button" className={s.close} onClick={onClose} aria-label="Close menu">
            <IconClose />
          </button>
        </div>

        {/* Not "Primary" — the desktop row already owns that name, and two
            landmarks with the same label are indistinguishable in a screen
            reader's landmark list even though only one is ever on screen. */}
        <nav className={s.nav} aria-label="Menu">
          <ul className={s.list}>
            {NAV_LINKS.map((item) => (
              <li key={item.to}>
                <Link className={s.link} to={item.to}>
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>

          {/* In-flow accordion, no focus trap needed — `<details>` is right
              here, and matches how the terminal header builds its menus. */}
          <details className={s.tools}>
            <summary className={s.summary}>
              Options Lab
              <IconChevronDown />
            </summary>
            <ul className={s.list}>
              {NAV_TOOLS.map((item) => (
                <li key={item.to}>
                  <Link className={s.sublink} to={item.to}>
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </details>
        </nav>

        <div className={s.actions}>
          <Link className={s.signup} to="/register">
            Create free account
          </Link>
          <Link className={s.login} to="/login">
            Sign in
          </Link>
        </div>
      </div>
    </dialog>
  );
}
