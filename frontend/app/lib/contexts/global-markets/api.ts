import { apiFetch } from '$shared/api/client';
import type { GlobalView } from './types';

/**
 * One read for the whole page.
 *
 * The timeline, the pressure gauge and the implied-open card all describe the
 * same instant, so they come from one request. Three separately polled
 * endpoints would let them drift apart on screen for reasons no user could
 * diagnose.
 */
export function getGlobalView(fetcher?: typeof fetch): Promise<GlobalView> {
  return apiFetch<GlobalView>({ url: '/global/view', fetcher });
}
