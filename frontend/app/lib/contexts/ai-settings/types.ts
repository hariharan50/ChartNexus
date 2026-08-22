/**
 * Per-user AI (LLM) settings.
 *
 * The raw API key is never present here: the backend stores it encrypted and
 * only ever returns it masked.
 */

export type LlmProvider = 'anthropic' | 'openai' | 'openrouter';

export interface AiSettings {
  provider: LlmProvider;
  model: string;
  /** A key is stored, so the agent tabs can run. */
  configured: boolean;
  /** Stored *and* on a provider we can actually run (Anthropic today). */
  available: boolean;
  masked_api_key: string | null;
}

export interface SaveAiSettingsInput {
  provider: LlmProvider;
  api_key: string;
  model: string;
}
