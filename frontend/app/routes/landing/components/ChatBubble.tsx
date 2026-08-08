import { Link } from 'react-router';
import IconMessage from '$shared/ui/icons/IconMessage';
import s from './ChatBubble.module.css';

/**
 * A link to help, not a chat widget.
 *
 * The design asks for a support bubble in the corner. There is no support desk
 * behind it, and a panel that opens, asks how it can help, and then cannot is
 * worse than an honest link to the help page.
 */
export default function ChatBubble() {
  return (
    <Link className={s.bubble} to="/settings/help" aria-label="Help and support">
      <IconMessage />
    </Link>
  );
}
