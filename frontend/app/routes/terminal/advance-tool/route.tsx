import { Link } from 'react-router';
import IconMessage from '$shared/ui/icons/IconMessage';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Advance Tools · ChartNexus' }];

/**
 * The Advance Tools landing — a grid of tool boxes reachable from the main nav.
 * Each box links to the tool's own page. First tool: Messaging Channels (the same
 * workflow available in Settings, surfaced here as a first-class tool).
 */
export default function AdvanceTools() {
  return (
    <div className={s.page}>
      <header className={s.head}>
        <h1 className={s.title}>Advance Tools</h1>
        <p className={s.sub}>
          Power tools for your desk. Open one to use it — more will land here over time.
        </p>
      </header>

      <div className={s.grid}>
        <Link to="/advance-tool/channels" className={s.box}>
          <span className={s.boxIcon} aria-hidden="true">
            <IconMessage />
          </span>
          <div className={s.boxText}>
            <span className={s.boxTitle}>Messaging Channels</span>
            <span className={s.boxDesc}>
              Connect Telegram (WhatsApp soon) and get your MME100 pre-market briefing pushed
              straight to your chat.
            </span>
            <span className={s.boxTag}>Telegram · live</span>
          </div>
        </Link>
      </div>
    </div>
  );
}
