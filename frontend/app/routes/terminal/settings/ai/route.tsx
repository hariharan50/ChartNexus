import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import * as ai from '$contexts/ai-settings/api';
import type { AiSettings, LlmProvider } from '$contexts/ai-settings/types';
import { presentAuthError } from '$contexts/identity/messages';
import Button from '$shared/ui/Button';
import { cx } from '$shared/ui/cx';
import IconAlert from '$shared/ui/icons/IconAlert';
import IconCheck from '$shared/ui/icons/IconCheck';
import PasswordField from '$shared/ui/PasswordField';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'AI Settings · MarketCompass' }];

type AuthError = ReturnType<typeof presentAuthError>;
type Busy = 'save' | 'clear' | null;

/** Providers. Only Claude is wired end-to-end today; the rest are reserved. */
const PROVIDERS: { id: LlmProvider; label: string; enabled: boolean }[] = [
  { id: 'anthropic', label: 'Claude (Anthropic)', enabled: true },
  { id: 'openai', label: 'OpenAI · GPT (coming soon)', enabled: false },
  { id: 'openrouter', label: 'OpenRouter (coming soon)', enabled: false }
];

/** Claude models offered for the Anthropic provider. */
const CLAUDE_MODELS: { id: string; label: string }[] = [
  { id: 'claude-opus-5', label: 'Claude Opus 5 — most capable' },
  { id: 'claude-sonnet-5', label: 'Claude Sonnet 5 — balanced (recommended)' },
  { id: 'claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5 — fastest' }
];

const DEFAULT_MODEL = 'claude-sonnet-5';

export default function SettingsAi() {
  const queryClient = useQueryClient();

  const [settings, setSettings] = useState<AiSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState<Busy>(null);
  const [error, setError] = useState<AuthError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const [provider, setProvider] = useState<LlmProvider>('anthropic');
  const [model, setModel] = useState<string>(DEFAULT_MODEL);
  const [apiKey, setApiKey] = useState('');

  const configured = !!settings?.configured;

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const result = await ai.getAiSettings();
      setSettings(result);
      setProvider(result.provider);
      setModel(result.model || DEFAULT_MODEL);
    } catch (caught) {
      setError(presentAuthError(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  // Saving or clearing a key flips the agents on or off. Drop the cached
  // availability so the AI Console un-gates (or re-gates) without a reload.
  function invalidateAvailability() {
    void queryClient.invalidateQueries({ queryKey: ['copilot', 'availability'] });
    void queryClient.invalidateQueries({ queryKey: ['stryx', 'availability'] });
  }

  async function run<T>(kind: Busy, action: () => Promise<T>): Promise<T | undefined> {
    setBusy(kind);
    setError(null);
    setNotice(null);
    try {
      return await action();
    } catch (caught) {
      setError(presentAuthError(caught));
      return undefined;
    } finally {
      setBusy(null);
    }
  }

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const result = await run('save', () =>
      ai.saveAiSettings({ provider, api_key: apiKey.trim(), model })
    );
    if (result) {
      setSettings(result);
      // The key is write-only from here on: the API will never return it.
      setApiKey('');
      setNotice('AI settings saved. The AI Console is ready.');
      invalidateAvailability();
    }
  }

  async function removeKey() {
    const result = await run('clear', () => ai.clearApiKey());
    if (result) {
      setSettings(result);
      setNotice('API key removed. The AI Console is disabled until you add one.');
      invalidateAvailability();
    }
  }

  const statusClass = configured ? s.configured : s.empty;
  const statusLabel = configured ? 'Configured' : 'Not configured';
  const headline = loading
    ? 'Checking…'
    : configured
      ? `Running on ${labelFor(settings?.provider)} · ${settings?.model}`
      : 'Add your own LLM key to turn the AI Console on';

  return (
    <section className={s.page}>
      <header>
        <h1>AI settings</h1>
        <p>
          The AI Console (Hella and STRYX) runs on <strong>your own</strong> LLM key. Add one below;
          it is stored encrypted and never shown to your browser again.
        </p>
      </header>

      {error ? (
        <div className={cx(s.banner, s.error)} role="alert">
          <span aria-hidden="true">
            <IconAlert />
          </span>
          <p>{error.message}</p>
        </div>
      ) : null}

      {notice ? (
        <div className={cx(s.banner, s.ok)} role="status">
          <span aria-hidden="true">
            <IconCheck />
          </span>
          <p>{notice}</p>
        </div>
      ) : null}

      <article className={cx(s.card, s.statusCard)}>
        <div className={s.statusHead}>
          <span className={cx(s.pill, statusClass)}>{statusLabel}</span>
          <strong>{headline}</strong>
        </div>

        {configured && settings?.masked_api_key ? (
          <dl>
            <div>
              <dt>Provider</dt>
              <dd>{labelFor(settings.provider)}</dd>
            </div>
            <div>
              <dt>Model</dt>
              <dd className="mc-numeric">{settings.model}</dd>
            </div>
            <div>
              <dt>API key</dt>
              <dd className="mc-numeric">{settings.masked_api_key}</dd>
            </div>
          </dl>
        ) : null}

        {configured ? (
          <div className={s.actions}>
            <Button variant="ghost" onClick={removeKey} loading={busy === 'clear'}>
              Remove key
            </Button>
          </div>
        ) : null}
      </article>

      <article className={s.card}>
        <h2>{configured ? 'Update your LLM key' : 'Add your LLM key'}</h2>

        <form className={s.form} onSubmit={save}>
          <label className={s.formField}>
            <span className={s.fieldLabel}>Provider</span>
            <select
              className={s.select}
              value={provider}
              onChange={(event) => setProvider(event.currentTarget.value as LlmProvider)}
            >
              {PROVIDERS.map((option) => (
                <option key={option.id} value={option.id} disabled={!option.enabled}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <label className={s.formField}>
            <span className={s.fieldLabel}>Model</span>
            <select
              className={s.select}
              value={model}
              onChange={(event) => setModel(event.currentTarget.value)}
            >
              {CLAUDE_MODELS.map((option) => (
                <option key={option.id} value={option.id}>
                  {option.label}
                </option>
              ))}
            </select>
          </label>

          <PasswordField
            className={s.formField}
            label="API key"
            value={apiKey}
            onValueChange={setApiKey}
            placeholder={configured ? 'Enter a new key to replace the stored one' : 'sk-ant-…'}
            autocomplete="new-password"
            required
          />
          <p className={s.hint}>
            Stored encrypted (AES-256-GCM). It is never shown again and never sent back to your
            browser. Get a Claude key at{' '}
            <a
              href="https://console.anthropic.com/settings/keys"
              target="_blank"
              rel="noreferrer noopener"
            >
              console.anthropic.com
            </a>
            .
          </p>
          <Button type="submit" loading={busy === 'save'}>
            {configured ? 'Update key' : 'Save key'}
          </Button>
        </form>
      </article>
    </section>
  );
}

function labelFor(provider: string | undefined): string {
  return PROVIDERS.find((option) => option.id === provider)?.label ?? 'Claude (Anthropic)';
}
