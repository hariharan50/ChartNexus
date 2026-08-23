import MessagingChannelsPanel from '../../components/MessagingChannelsPanel';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Messaging Channels · MarketCompass' }];

export default function SettingsChannels() {
  return <MessagingChannelsPanel />;
}
