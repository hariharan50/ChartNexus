import { apiFetch } from '$shared/api/client';
import type { ChannelName, ChannelsResponse, ChannelView } from './types';

/** Messaging channels — connect and manage where updates are delivered. */

export function getChannels(fetcher?: typeof fetch): Promise<ChannelsResponse> {
  return apiFetch<ChannelsResponse>({ url: '/messaging/channels', fetcher });
}

/** Save (and verify) the user's Telegram bot token. */
export function connectTelegram(botToken: string): Promise<ChannelView> {
  return apiFetch<ChannelView>({
    url: '/messaging/telegram',
    method: 'PUT',
    body: JSON.stringify({ bot_token: botToken })
  });
}

/** Link the chat to deliver to — auto-detected, or a manual chat id. */
export function detectTelegramChat(chatId?: string): Promise<ChannelView> {
  return apiFetch<ChannelView>({
    url: '/messaging/telegram/detect-chat',
    method: 'POST',
    body: JSON.stringify({ chat_id: chatId ?? null })
  });
}

/** Send a test message to confirm the connection end-to-end. */
export function sendTelegramTest(): Promise<void> {
  return apiFetch<void>({ url: '/messaging/telegram/test', method: 'POST', body: '{}' });
}

/** Enable or disable delivery to a channel. */
export function setChannelEnabled(channel: ChannelName, enabled: boolean): Promise<ChannelView> {
  return apiFetch<ChannelView>({
    url: `/messaging/channels/${channel}`,
    method: 'PATCH',
    body: JSON.stringify({ enabled })
  });
}

/** Disconnect a channel. */
export function disconnectChannel(channel: ChannelName): Promise<void> {
  return apiFetch<void>({ url: `/messaging/channels/${channel}`, method: 'DELETE' });
}
