import MessagingChannelsPanel from '../../components/MessagingChannelsPanel';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Messaging Channels · ChartNexus' }];

export default function SettingsChannels() {
  return <MessagingChannelsPanel />;
}
