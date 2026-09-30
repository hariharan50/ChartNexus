import { apiFetch } from '$shared/api/client';
import type { PreMarketView } from './types';

/**
 * One read for the whole screener.
 *
 * The regime score, the level ladder and the gap cards all describe the same
 * instant. Eleven separately polled endpoints would let them disagree on
 * screen for reasons no user could diagnose — the same reasoning GIA's single
 * endpoint rests on, with more panels at stake.
 */
export function getPreMarketView(focus: string, fetcher?: typeof fetch): Promise<PreMarketView> {
  return apiFetch<PreMarketView>({
    url: `/pre-market/view?focus=${encodeURIComponent(focus)}`,
    fetcher
  });
}
