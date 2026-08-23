import { Link } from 'react-router';
import MessagingChannelsPanel from '../components/MessagingChannelsPanel';
import s from './route.module.css';
import type { Route } from './+types/channels';

export const meta: Route.MetaFunction = () => [
  { title: 'Messaging Channels · Advance Tools · MarketCompass' }
];

/** The Messaging Channels tool, opened from the Advance Tools grid. Renders the
 *  exact same workflow as Settings → Messaging Channels. */
export default function AdvanceToolChannels() {
  return (
    <div className={s.toolPage}>
      <div className={s.toolInner}>
        <Link to="/advance-tool" className={s.back}>
          ← Advance Tools
        </Link>
        <MessagingChannelsPanel />
      </div>
    </div>
  );
}
