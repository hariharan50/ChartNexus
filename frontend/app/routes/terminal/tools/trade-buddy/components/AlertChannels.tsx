import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import Button from '$shared/ui/Button';
import { cx } from '$shared/ui/cx';
import PasswordField from '$shared/ui/PasswordField';
import TextField from '$shared/ui/TextField';
import {
  CHANNEL_STEP_COPY,
  channelStep,
  connectTelegram,
  disconnectChannel,
  getChannels,
  linkTelegramChat,
  setChannelEnabled,
  testChannel,
  type AlertChannelView,
  type ChannelsResponse
} from '../trade-buddy-data';
import s from './AlertChannels.module.css';

/**
 * Trade Buddy's own Telegram bot — deliberately not the one under
 * Settings → Channels.
 *
 * Two bots rather than one because the two message kinds want different
 * treatment on a phone: a level break arrives mid-trade and should buzz, a
 * pre-market briefing arrives once and should not. Sharing a bot would mean
 * one notification setting for both, so silencing the briefing would silence
 * the alerts that matter.
 *
 * The flow is the same four steps as the Channels page, because it is the
 * same problem: paste the token → it is verified with Telegram → link the
 * chat to deliver to → prove it works. The panel shows which step you are on
 * rather than making you infer it from which fields are filled.
 */
export default function AlertChannels() {
  const queryClient = useQueryClient();
  const [token, setToken] = useState('');
  const [manualChat, setManualChat] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const channels = useQuery<ChannelsResponse>({
    queryKey: ['trade-buddy', 'channels'],
    queryFn: getChannels
  });

  const telegram: AlertChannelView | undefined = channels.data?.channels.find(
    (c) => c.channel === 'telegram'
  );
  const step = channelStep(telegram);

  async function refresh() {
    await queryClient.invalidateQueries({ queryKey: ['trade-buddy', 'channels'] });
  }

  function handle<T>(fn: () => Promise<T>, success: string) {
    return async () => {
      setError(null);
      setNotice(null);
      try {
        await fn();
        setNotice(success);
        await refresh();
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : String(cause));
      }
    };
  }

  const connect = useMutation({
    mutationFn: handle(() => connectTelegram(token.trim()), 'Bot token saved and verified.'),
    onSuccess: () => setToken('')
  });

  const link = useMutation({
    mutationFn: handle(
      () => linkTelegramChat(manualChat.trim() || null),
      'Chat linked — a welcome message has been sent. Check Telegram.'
    ),
    onSuccess: () => setManualChat('')
  });

  const test = useMutation({
    mutationFn: handle(testChannel, 'Test sent — check Telegram.')
  });

  const toggle = useMutation({
    mutationFn: handle(
      () => setChannelEnabled('telegram', !(telegram?.enabled ?? true)),
      telegram?.enabled ? 'Alerts paused.' : 'Alerts resumed.'
    )
  });

  const forget = useMutation({
    mutationFn: handle(() => disconnectChannel('telegram'), 'Bot disconnected.')
  });

  const busy =
    connect.isPending || link.isPending || test.isPending || toggle.isPending || forget.isPending;

  return (
    <section className={s.panel} aria-labelledby="tb-channels">
      <header className={s.head}>
        <h2 id="tb-channels" className={s.title}>
          Alert channel
        </h2>
        <p className={s.note}>
          A bot of its own, separate from the one under Settings → Channels. Level alerts arrive
          mid-trade and the pre-market briefing arrives once, so they want different notification
          settings on your phone — one bot could not do both.
        </p>
      </header>

      {/* Step first, in words: which of the four states you are in is the
          thing you need, and inferring it from which fields are filled is
          exactly the guessing this replaces. */}
      <div className={cx(s.status, s[`step_${step}`])}>
        <span className={s.dot} aria-hidden="true" />
        <div>
          <p className={s.statusLabel}>
            Telegram · {CHANNEL_STEP_COPY[step].label}
            {telegram?.label && <span className={s.bot}> {telegram.label}</span>}
          </p>
          <p className={s.statusDetail}>{CHANNEL_STEP_COPY[step].detail}</p>
        </div>
      </div>

      {(error || notice) && (
        <p className={cx(s.banner, error ? s.bannerError : s.bannerOk)} role="status">
          {error ?? notice}
        </p>
      )}

      {/* -- step 1: the token --------------------------------------------- */}
      <div className={s.step}>
        <PasswordField
          label={telegram?.configured ? 'Replace bot token' : 'Bot token'}
          value={token}
          onValueChange={setToken}
          placeholder={telegram?.masked_secret ?? '8123456789:AAH…'}
          autocomplete="new-password"
        />
        <p className={s.hint}>
          Message <strong>@BotFather</strong> on Telegram, send <code>/newbot</code>, and paste the
          token it gives you. It is verified with Telegram before it is stored.
        </p>
        <Button
          onClick={() => connect.mutate()}
          loading={connect.isPending}
          disabled={busy || token.trim().length < 10}
        >
          {telegram?.configured ? 'Replace token' : 'Save token'}
        </Button>
      </div>

      {/* -- step 2: the chat ---------------------------------------------- */}
      {telegram?.configured && (
        <div className={s.step}>
          <p className={s.stepTitle}>Where alerts go</p>
          {telegram.target ? (
            <p className={s.hint}>
              Linked to chat <code>{telegram.target}</code>.
            </p>
          ) : (
            <p className={s.hint}>
              Send your bot any message first — a bot cannot open a conversation — then link
              automatically, or paste a chat id. Linking delivers a welcome message, so the chat is
              only saved once it has actually received one.
            </p>
          )}
          <div className={s.row}>
            <TextField
              label="Chat id — a number, not a message"
              value={manualChat}
              onValueChange={setManualChat}
              placeholder="leave blank to detect · or e.g. 123456789"
              inputMode="numeric"
              className={s.chatField}
            />
            <Button variant="secondary" onClick={() => link.mutate()} loading={link.isPending}>
              {telegram.target ? 'Relink' : 'Link chat'}
            </Button>
          </div>
        </div>
      )}

      {/* -- step 3: prove it ---------------------------------------------- */}
      {telegram?.ready && (
        <div className={s.step}>
          <p className={s.stepTitle}>Confirm it works</p>
          <p className={s.hint}>
            Sends through the same path a real alert takes, so a message arriving proves the token,
            the chat and the formatting — not just that a row exists.
          </p>
          <Button onClick={() => test.mutate()} loading={test.isPending} disabled={busy}>
            Send test message
          </Button>
        </div>
      )}

      {telegram?.configured && (
        <div className={s.actions}>
          <Button variant="ghost" onClick={() => toggle.mutate()} loading={toggle.isPending}>
            {telegram.enabled ? 'Pause alerts' : 'Resume alerts'}
          </Button>
          <Button variant="ghost" onClick={() => forget.mutate()} loading={forget.isPending}>
            Disconnect
          </Button>
        </div>
      )}
    </section>
  );
}
