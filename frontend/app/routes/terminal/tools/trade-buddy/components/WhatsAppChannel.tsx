import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import Button from '$shared/ui/Button';
import { cx } from '$shared/ui/cx';
import PasswordField from '$shared/ui/PasswordField';
import TextField from '$shared/ui/TextField';
import {
  connectWhatsApp,
  disconnectChannel,
  setChannelEnabled,
  testWhatsApp,
  type AlertChannelView
} from '../trade-buddy-data';
import s from './AlertChannels.module.css';

/**
 * Your own WhatsApp, through the free CallMeBot relay.
 *
 * Per user, like the Telegram bot above it: the number and the CallMeBot key
 * are stored encrypted against your account and are never sent back — the card
 * shows the last four digits only.
 *
 * Connecting is one step because CallMeBot has no "verify" call: the server
 * sends a welcome message, and stores nothing unless it was accepted. So a card
 * that says Ready has already delivered once.
 *
 * WhatsApp gets confirmed facts only (breaks, reclaims, gaps), within a
 * rolling allowance — Telegram gets everything.
 */
interface Props {
  whatsapp: AlertChannelView | undefined;
}

export default function WhatsAppChannel({ whatsapp }: Props) {
  const queryClient = useQueryClient();
  const [phone, setPhone] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function handle<T>(fn: () => Promise<T>, success: string) {
    return async () => {
      setError(null);
      setNotice(null);
      try {
        await fn();
        setNotice(success);
        await queryClient.invalidateQueries({ queryKey: ['trade-buddy', 'channels'] });
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : String(cause));
      }
    };
  }

  const connect = useMutation({
    mutationFn: handle(
      () => connectWhatsApp(phone.trim(), apiKey.trim()),
      'WhatsApp connected — a welcome message has been sent.'
    ),
    onSuccess: () => {
      setPhone('');
      setApiKey('');
      setShowForm(false);
    }
  });
  const test = useMutation({
    mutationFn: handle(testWhatsApp, 'Test sent — check WhatsApp.')
  });
  const toggle = useMutation({
    mutationFn: handle(
      () => setChannelEnabled('whatsapp', !(whatsapp?.enabled ?? true)),
      whatsapp?.enabled ? 'WhatsApp alerts paused.' : 'WhatsApp alerts resumed.'
    )
  });
  const forget = useMutation({
    mutationFn: handle(() => disconnectChannel('whatsapp'), 'WhatsApp disconnected.')
  });

  const busy = connect.isPending || test.isPending || toggle.isPending || forget.isPending;
  const connected = Boolean(whatsapp?.configured);
  const formOpen = !connected || showForm;
  const status = !connected ? 'Not connected' : !whatsapp?.enabled ? 'Paused' : 'Ready';

  return (
    <div className={s.channel}>
      <span className={s.tile} aria-hidden="true">
        <svg viewBox="0 0 24 24" className={s.tileIcon}>
          <path
            d="M4 20l1.3-3.9A8 8 0 1 1 8 19l-4 1Z"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.6"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      <div className={s.channelBody}>
        <p className={s.channelName}>
          WhatsApp
          <span className={s.bot}> · {status}</span>
        </p>
        {connected && whatsapp?.target && (
          <p className={s.channelDetail}>
            {'number '}
            <code className={s.code}>{whatsapp.target}</code>
            {whatsapp.masked_secret && (
              <>
                {' · key '}
                <code className={s.code}>{whatsapp.masked_secret}</code>
              </>
            )}
          </p>
        )}
        {connected && !whatsapp?.enabled && (
          <p className={s.channelDetail}>Connected, but switched off.</p>
        )}

        {(error || notice) && (
          <p className={cx(s.banner, error ? s.bannerError : s.bannerOk)} role="status">
            {error ?? notice}
          </p>
        )}

        {formOpen && (
          <div className={s.step}>
            <TextField
              label="WhatsApp number, with country code"
              value={phone}
              onValueChange={setPhone}
              placeholder="+91 98765 43210"
              inputMode="tel"
            />
            <PasswordField
              label="CallMeBot API key"
              value={apiKey}
              onValueChange={setApiKey}
              placeholder={whatsapp?.masked_secret ?? 'the key CallMeBot sends you'}
              autocomplete="new-password"
            />
            <p className={s.hint}>
              Follow{' '}
              <a
                href="https://www.callmebot.com/blog/free-api-whatsapp-messages/"
                target="_blank"
                rel="noopener noreferrer"
              >
                CallMeBot&apos;s setup
              </a>{' '}
              to activate your number — it replies on WhatsApp with your API key. Both are stored
              encrypted and are never shown again in full.
            </p>
            <div className={s.row}>
              <Button
                onClick={() => connect.mutate()}
                loading={connect.isPending}
                disabled={busy || phone.trim().length < 8 || apiKey.trim().length < 4}
              >
                {connected ? 'Replace and verify' : 'Connect WhatsApp'}
              </Button>
              {connected && (
                <Button variant="ghost" onClick={() => setShowForm(false)}>
                  Cancel
                </Button>
              )}
            </div>
          </div>
        )}

        {connected && (
          <div className={s.actions}>
            {whatsapp?.ready && (
              <Button onClick={() => test.mutate()} loading={test.isPending} disabled={busy}>
                Send test message
              </Button>
            )}
            <Button variant="ghost" onClick={() => toggle.mutate()} loading={toggle.isPending}>
              {whatsapp?.enabled ? 'Pause' : 'Resume alerts'}
            </Button>
            {!showForm && (
              <Button variant="ghost" onClick={() => setShowForm(true)}>
                Change number
              </Button>
            )}
            <Button variant="ghost" onClick={() => forget.mutate()} loading={forget.isPending}>
              Disconnect
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
