import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import Button from '$shared/ui/Button';
import { cx } from '$shared/ui/cx';
import PasswordField from '$shared/ui/PasswordField';
import Select from '$shared/ui/Select';
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
  type AlertKind,
  type ChannelsResponse
} from '../trade-buddy-data';
import s from './AlertChannels.module.css';

/**
 * Where the alerts go — Trade Buddy's own Telegram bot, deliberately not the
 * one under Settings → Channels.
 *
 * Two bots rather than one because the two message kinds want different
 * treatment on a phone: a level break arrives mid-trade and should buzz, a
 * pre-market briefing arrives once and should not. Sharing a bot would mean
 * one notification setting for both, so silencing the briefing would silence
 * the alerts that matter.
 *
 * The flow is four steps — paste the token, it is verified with Telegram, link
 * the chat, prove it works — and the card shows which one you are on rather
 * than making you infer it from which fields are filled. Once connected, the
 * token form folds away behind a disclosure: replacing a working token is the
 * rarest thing anyone does here, and leaving an empty password field at the
 * top of the card made a finished setup look unfinished.
 *
 * The test row lives here too, beside the channel it exercises. It was next to
 * the levels, which put "does my phone work" in the middle of "where is
 * price".
 */
interface Props {
  symbol: string;
  testKind: AlertKind;
  onTestKindChange: (kind: AlertKind) => void;
  /** Fires a synthetic alert for the selected symbol through the real router. */
  onTest: () => void;
  testing: boolean;
  /** False with no levels marked: there would be nothing to alert about. */
  canTest: boolean;
  whatsappUsed: number | undefined;
  whatsappLimit: number | undefined;
}

const TEST_KINDS: { value: AlertKind; label: string }[] = [
  { value: 'touched', label: 'Touched (Telegram only)' },
  { value: 'approaching', label: 'Approaching (Telegram only)' },
  { value: 'break_confirmed', label: 'Break confirmed (also WhatsApp)' }
];

export default function AlertChannels({
  symbol,
  testKind,
  onTestKindChange,
  onTest,
  testing,
  canTest,
  whatsappUsed,
  whatsappLimit
}: Props) {
  const queryClient = useQueryClient();
  const [token, setToken] = useState('');
  const [manualChat, setManualChat] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [showToken, setShowToken] = useState(false);

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
    onSuccess: () => {
      setToken('');
      setShowToken(false);
    }
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
  // Not yet connected: the token form is the whole card, so there is nothing
  // for a disclosure to hide.
  const tokenFormOpen = !telegram?.configured || showToken;

  return (
    <section className={s.card} aria-labelledby="tb-channels">
      <header className={s.head}>
        <h2 id="tb-channels" className={s.title}>
          Delivery
        </h2>
        <span className={cx(s.pill, s[`step_${step}`])}>{CHANNEL_STEP_COPY[step].label}</span>
      </header>

      <div className={s.channel}>
        <span className={s.tile} aria-hidden="true">
          <svg viewBox="0 0 24 24" className={s.tileIcon}>
            <path
              d="M21 4 2.8 11.2l5.5 1.9L21 4Zm0 0-9.1 12.4-.3 4.4-2.3-5.7L21 4Z"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <div className={s.channelBody}>
          <p className={s.channelName}>
            Telegram
            {telegram?.label && <span className={s.bot}> · {telegram.label}</span>}
          </p>
          {telegram?.masked_secret && (
            <p className={s.channelDetail}>
              <code className={s.code}>{telegram.masked_secret}</code>
              {telegram.target && (
                <>
                  {' · chat '}
                  <code className={s.code}>{telegram.target}</code>
                </>
              )}
            </p>
          )}
          {/* What the step means, whenever it is not simply working. Paused is
              the case that needs it most: a connected-but-silent channel is
              the state most easily mistaken for a fault, and the credentials
              line above says nothing about it. */}
          {step !== 'ready' && <p className={s.channelDetail}>{CHANNEL_STEP_COPY[step].detail}</p>}
        </div>
      </div>

      {(error || notice) && (
        <p className={cx(s.banner, error ? s.bannerError : s.bannerOk)} role="status">
          {error ?? notice}
        </p>
      )}

      {/* -- step 1: the token --------------------------------------------- */}
      {tokenFormOpen ? (
        <div className={s.step}>
          <PasswordField
            label={telegram?.configured ? 'Replace bot token' : 'Bot token'}
            value={token}
            onValueChange={setToken}
            placeholder={telegram?.masked_secret ?? '8123456789:AAH…'}
            autocomplete="new-password"
          />
          <p className={s.hint}>
            Message <strong>@BotFather</strong> on Telegram, send <code>/newbot</code>, and paste
            the token it gives you. It is verified with Telegram before it is stored.
          </p>
          <div className={s.row}>
            <Button
              onClick={() => connect.mutate()}
              loading={connect.isPending}
              disabled={busy || token.trim().length < 10}
            >
              {telegram?.configured ? 'Replace token' : 'Save token'}
            </Button>
            {telegram?.configured && (
              <Button variant="ghost" onClick={() => setShowToken(false)}>
                Cancel
              </Button>
            )}
          </div>
        </div>
      ) : null}

      {/* -- step 2: the chat ---------------------------------------------- */}
      {telegram?.configured && !telegram.target && (
        <div className={s.step}>
          <p className={s.stepTitle}>Where alerts go</p>
          <p className={s.hint}>
            Send your bot any message first — a bot cannot open a conversation — then link
            automatically, or paste a chat id. Linking delivers a welcome message, so the chat is
            only saved once it has actually received one.
          </p>
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
              Link chat
            </Button>
          </div>
        </div>
      )}

      {/* -- the actions on a working channel ------------------------------ */}
      {telegram?.configured && (
        <div className={s.actions}>
          {telegram.ready && (
            <Button onClick={() => test.mutate()} loading={test.isPending} disabled={busy}>
              Send test message
            </Button>
          )}
          {telegram.target && (
            <Button variant="ghost" onClick={() => link.mutate()} loading={link.isPending}>
              Relink
            </Button>
          )}
          <Button variant="ghost" onClick={() => toggle.mutate()} loading={toggle.isPending}>
            {telegram.enabled ? 'Pause' : 'Resume alerts'}
          </Button>
          {!showToken && (
            <Button variant="ghost" onClick={() => setShowToken(true)}>
              Replace token
            </Button>
          )}
          <Button variant="ghost" onClick={() => forget.mutate()} loading={forget.isPending}>
            Disconnect
          </Button>
        </div>
      )}

      {/* -- the level-alert test ------------------------------------------ */}
      <div className={s.step}>
        <p className={s.stepTitle}>Test a level alert</p>
        <div className={s.row}>
          <Select
            className={s.testSelect}
            value={testKind}
            ariaLabel="Test alert type"
            options={TEST_KINDS}
            onChange={onTestKindChange}
          />
          <Button variant="secondary" onClick={onTest} loading={testing} disabled={!canTest}>
            Send test alert
          </Button>
        </div>
        <p className={s.hint}>
          Fires one synthetic {symbol} alert through the real notifiers and the real channel policy,
          so a confirmed-break test also spends one WhatsApp message.
        </p>
      </div>

      {/* -- the WhatsApp budget ------------------------------------------- */}
      {whatsappLimit !== undefined && whatsappUsed !== undefined && (
        <div className={s.budget}>
          <p className={s.budgetHead}>
            WhatsApp budget
            <span className={s.budgetCount}>
              {whatsappUsed} / {whatsappLimit}
            </span>
          </p>
          <span className={s.meter} aria-hidden="true">
            <span
              className={s.meterFill}
              style={{
                width: `${whatsappLimit > 0 ? Math.min(100, (whatsappUsed / whatsappLimit) * 100) : 0}%`
              }}
            />
          </span>
          <p className={s.hint}>
            Rolling four-hour window. Telegram alerts don&apos;t count against it.
          </p>
        </div>
      )}

      <p className={s.footNote}>
        Separate from Settings → Channels so level alerts can have their own notification sound.
      </p>
    </section>
  );
}
