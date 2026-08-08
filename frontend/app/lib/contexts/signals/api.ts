import { apiFetch } from '$shared/api/client';
import type { AskResponse, Guidance, GuidanceHistory } from './types';

/** AI Market Guider — decision, factors, history, and the copilot chat. */

export function getGuidance(symbol: string, fetcher?: typeof fetch): Promise<Guidance> {
  return apiFetch<Guidance>({ url: `/signals/${symbol}/guidance`, fetcher });
}

export function getGuidanceHistory(
  symbol: string,
  limit = 50,
  fetcher?: typeof fetch
): Promise<GuidanceHistory> {
  return apiFetch<GuidanceHistory>({
    url: `/signals/${symbol}/history`,
    params: { limit },
    fetcher
  });
}

export function askAgent(symbol: string, question: string): Promise<AskResponse> {
  return apiFetch<AskResponse>({
    url: `/copilot/${symbol}/ask`,
    method: 'POST',
    body: JSON.stringify({ question })
  });
}
