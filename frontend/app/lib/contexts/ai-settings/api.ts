import { apiFetch } from '$shared/api/client';
import type { AiSettings, SaveAiSettingsInput } from './types';

/** The current user's AI settings (key masked). */
export function getAiSettings(fetcher?: typeof fetch): Promise<AiSettings> {
  return apiFetch<AiSettings>({ url: '/ai/settings', fetcher });
}

/** Save the provider, API key, and model. The key is write-only from here on. */
export function saveAiSettings(input: SaveAiSettingsInput): Promise<AiSettings> {
  return apiFetch<AiSettings>({
    url: '/ai/settings',
    method: 'PUT',
    body: JSON.stringify(input)
  });
}

/** Remove the stored key, disabling the agents until a new one is added. */
export function clearApiKey(): Promise<AiSettings> {
  return apiFetch<AiSettings>({ url: '/ai/settings/key', method: 'DELETE' });
}
