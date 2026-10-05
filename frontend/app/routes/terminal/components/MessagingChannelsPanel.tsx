import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router';
import * as messaging from '$contexts/messaging/api';
import type { ChannelView } from '$contexts/messaging/types';
import { presentAuthError } from '$contexts/identity/messages';
import Button from '$shared/ui/Button';
import { cx } from '$shared/ui/cx';
import IconAlert from '$shared/ui/icons/IconAlert';
import IconCheck from '$shared/ui/icons/IconCheck';
import PasswordField from '$shared/ui/PasswordField';
import TextField from '$shared/ui/TextField';
import s from '../settings/channels/route.module.css';

type Busy = 'save' | 'link' | 'linkManual' | 'test' | 'toggle' | 'disconnect' | null;

/**
 * The full "Messaging Channels" workflow — connect Telegram, link the chat, send a
 * test, enable/disable, disconnect. Shared so it renders identically in
 * Settings → Messaging Channels and on the Advance Tools page.
 */
export default function MessagingChannelsPanel() {
  const [channels, setChannels] = useState<ChannelView[] | null>(null);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [botToken, setBotToken] = useState('');
  const [manualChat, setManualChat] = useState('');

  const telegram = channels?.find((c) => c.channel === 'telegram') ?? null;

  const load = useCallback(async () => {
    try {
      const result = await messaging.getChannels();
      setChannels(result.channels);
    } catch (caught) {
      setError(presentAuthError(caught).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function run<T>(kind: Busy, action: () => Promise<T>): Promise<T | undefined> {
    setBusy(kind);
    setError(null);
    setNotice(null);
    try {
      return await action();
    } catch (caught) {
      setError(presentAuthError(caught).message);
      return undefined;
    } finally {
      setBusy(null);
    }
  }

  async function saveToken() {
    const result = await run('save', () => messaging.connectTelegram(botToken.trim()));
    if (result) {
      setBotToken('');
      setNotice(`Bot verified${result.label ? ` (${result.label})` : ''}. Now link your chat.`);
      await load();
    }
  }

  async function linkChat(manual: boolean) {
    const result = await run(manual ? 'linkManual' : 'link', () =>
      messaging.detectTelegramChat(manual ? manualChat.trim() : undefined)
    );
    if (result) {
      setManualChat('');
      setNotice('Chat linked. Send a test to confirm.');
      await load();
    }
  }

  async function sendTest() {
    const done = await run('test', () => messaging.sendTelegramTest());
    if (done !== undefined) setNotice('Test message sent — check your Telegram.');
  }

  async function toggle() {
    if (!telegram) return;
    const result = await run('toggle', () =>
      messaging.setChannelEnabled('telegram', !telegram.enabled)
    );
    if (result) await load();
  }

  async function disconnect() {
    const done = await run('disconnect', () => messaging.disconnectChannel('telegram'));
    if (done !== undefined) {
      setNotice('Telegram disconnected.');
      await load();
    }
  }

  const status = telegramStatus(telegram);

  return (
    <div className={s.page}>
      <header className={s.head}>
        <h1 className={s.title}>Messaging Channels</h1>
        <p className={s.sub}>
          Connect a chat app to receive your ChartNexus updates — starting with the daily{' '}
          <Link to="/ai-console/mme100">MME100 pre-market briefing</Link>. Turn the briefing
          automation on under <Link to="/settings/power-agents">Power AI Agents</Link>.
        </p>
      </header>

      {error ? (
        <div className={cx(s.banner, s.error)} role="alert">
          <IconAlert />
          <p>{error}</p>
        </div>
      ) : null}
      {notice ? (
        <div className={cx(s.banner, s.ok)} role="status">
          <IconCheck />
          <p>{notice}</p>
        </div>
      ) : null}

      {/* -- Telegram ------------------------------------------------------- */}
      <section className={s.card}>
        <div className={s.cardHead}>
          <span className={s.mark}>T</span>
          <div>
            <h2 className={s.cardTitle}>Telegram</h2>
            <span className={s.cardKicker}>
              {telegram?.label ? telegram.label : 'Free · a bot you create with @BotFather'}
            </span>
          </div>
          <span className={cx(s.statusPill, status.className)}>{status.label}</span>
        </div>

        {/* Step 1 — bot token */}
        <div className={s.step}>
          <span className={s.stepNum}>1</span>
          <div className={s.stepBody}>
            <span className={s.stepTitle}>Paste your bot token</span>
            <p className={s.hint}>
              In Telegram, open <span className={s.code}>@BotFather</span>, send{' '}
              <span className={s.code}>/newbot</span>, and copy the token it gives you (looks like{' '}
              <span className={s.code}>123456789:AA…</span>).
            </p>
            <div className={s.row}>
              <PasswordField
                className={s.grow}
                label="Bot token"
                value={botToken}
                onValueChange={setBotToken}
                placeholder={
                  telegram?.configured ? 'Enter a new token to replace it' : '123456789:AA…'
                }
                autocomplete="new-password"
              />
              <Button onClick={saveToken} loading={busy === 'save'} disabled={!botToken.trim()}>
                {telegram?.configured ? 'Update token' : 'Save token'}
              </Button>
            </div>
          </div>
        </div>

        {/* Step 2 — link chat */}
        {telegram?.configured ? (
          <div className={s.step}>
            <span className={s.stepNum}>2</span>
            <div className={s.stepBody}>
              <span className={s.stepTitle}>Link your chat</span>
              <p className={s.hint}>
                Open Telegram and send <span className={s.code}>/start</span> (or any message) to
                your bot, then tap Link my chat.{' '}
                {telegram.target ? (
                  <>
                    Linked to chat <span className={s.code}>{telegram.target}</span>.
                  </>
                ) : null}
              </p>
              <div className={s.actions}>
                <Button onClick={() => linkChat(false)} loading={busy === 'link'}>
                  Link my chat
                </Button>
              </div>
              <div className={s.row}>
                <TextField
                  className={s.grow}
                  label="…or paste your chat id"
                  value={manualChat}
                  onValueChange={setManualChat}
                  placeholder="e.g. 123456789"
                  inputMode="numeric"
                />
                <Button
                  variant="ghost"
                  onClick={() => linkChat(true)}
                  loading={busy === 'linkManual'}
                  disabled={!manualChat.trim()}
                >
                  Use this id
                </Button>
              </div>
            </div>
          </div>
        ) : null}

        {/* Step 3 — test + enable */}
        {telegram?.verified ? (
          <div className={s.step}>
            <span className={s.stepNum}>3</span>
            <div className={s.stepBody}>
              <span className={s.stepTitle}>Confirm &amp; enable</span>
              <div className={s.actions}>
                <Button onClick={sendTest} loading={busy === 'test'}>
                  Send test message
                </Button>
              </div>
              <div className={s.toggleRow}>
                <span className={s.hint}>
                  {telegram.enabled
                    ? 'Delivery is on — updates will be sent here.'
                    : 'Delivery is off — no updates will be sent.'}
                </span>
                <button
                  type="button"
                  role="switch"
                  aria-checked={telegram.enabled}
                  aria-label="Toggle Telegram delivery"
                  className={cx(s.switch, telegram.enabled && s.switchOn)}
                  disabled={busy === 'toggle'}
                  onClick={toggle}
                >
                  <span className={s.knob} />
                </button>
              </div>
            </div>
          </div>
        ) : null}

        {telegram?.configured ? (
          <div className={s.actions}>
            <Button variant="ghost" onClick={disconnect} loading={busy === 'disconnect'}>
              Disconnect Telegram
            </Button>
          </div>
        ) : null}
      </section>

      {/* -- WhatsApp (coming soon) ---------------------------------------- */}
      <section className={cx(s.card, s.soon)}>
        <div className={s.cardHead}>
          <span className={s.mark} style={{ background: '#25d366' }}>
            W
          </span>
          <div>
            <h2 className={s.cardTitle}>WhatsApp</h2>
            <span className={s.cardKicker}>Official Business API — needs approved templates</span>
          </div>
          <span className={s.soonBadge}>Coming soon</span>
        </div>
        <p className={s.hint}>
          WhatsApp delivery is planned. It requires a WhatsApp Business account and message
          templates approved by Meta, so it&apos;s a later step — Telegram is ready today.
        </p>
      </section>
    </div>
  );
}

function telegramStatus(telegram: ChannelView | null): {
  label: string;
  className: string | undefined;
} {
  if (!telegram || !telegram.configured) return { label: 'Not connected', className: undefined };
  if (telegram.ready) return { label: 'Ready', className: s.statusReady };
  if (telegram.verified && !telegram.enabled)
    return { label: 'Paused', className: s.statusPartial };
  return { label: 'Chat not linked', className: s.statusPartial };
}
