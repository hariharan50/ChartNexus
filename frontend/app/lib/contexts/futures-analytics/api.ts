import { apiFetch } from '$shared/api/client';
import type { FuturesBoard, FuturesDashboard } from './types';

export function getFuturesDashboard(
  opts: { limit?: number; sector?: string } = {},
  fetcher?: typeof fetch
): Promise<FuturesDashboard> {
  const params: Record<string, string> = {};
  if (opts.limit) params.limit = String(opts.limit);
  if (opts.sector) params.sector = opts.sector;
  return apiFetch<FuturesDashboard>({ url: '/futures/dashboard', params, fetcher });
}

export function getFuturesBoard(
  opts: { sector?: string; kind?: 'index' | 'stock' } = {},
  fetcher?: typeof fetch
): Promise<FuturesBoard> {
  const params: Record<string, string> = {};
  if (opts.sector) params.sector = opts.sector;
  if (opts.kind) params.kind = opts.kind;
  return apiFetch<FuturesBoard>({ url: '/futures/board', params, fetcher });
}
