/** Wire types for messaging channels — the raw secret is never present. */

export type ChannelName = 'telegram' | 'whatsapp';

export type ChannelView = {
  channel: ChannelName;
  configured: boolean;
  verified: boolean;
  enabled: boolean;
  ready: boolean;
  label: string | null;
  target: string | null;
  masked_secret: string | null;
};

export type ChannelsResponse = {
  channels: ChannelView[];
};
