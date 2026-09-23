import { apiFetch } from '$shared/api/client';
import type { ExpiryList, FuturesBoard, FuturesDashboard } from './types';

export function getFuturesDashboard(
  opts: { limit?: number; sector?: string; series?: number } = {},
  fetcher?: typeof fetch
): Promise<FuturesDashboard> {
  const params: Record<string, string> = {};
  if (opts.limit) params.limit = String(opts.limit);
  if (opts.sector) params.sector = opts.sector;
  // Sent only when it is not the near month, so the default request URL — and
  // therefore the server's own default — stays exactly what it was.
  if (opts.series) params.series = String(opts.series);
  return apiFetch<FuturesDashboard>({ url: '/futures/dashboard', params, fetcher });
}

export function getFuturesBoard(
  opts: { sector?: string; kind?: 'index' | 'stock'; series?: number } = {},
  fetcher?: typeof fetch
): Promise<FuturesBoard> {
  const params: Record<string, string> = {};
  if (opts.sector) params.sector = opts.sector;
  if (opts.kind) params.kind = opts.kind;
  if (opts.series) params.series = String(opts.series);
  return apiFetch<FuturesBoard>({ url: '/futures/board', params, fetcher });
}

/**
 * The contract series the board can be drawn for, nearest first.
 *
 * Read from the catalog server-side, so this costs no broker request and can
 * be fetched by every page that shows the picker.
 */
export function getFuturesExpiries(fetcher?: typeof fetch): Promise<ExpiryList> {
  return apiFetch<ExpiryList>({ url: '/futures/expiries', fetcher });
}
