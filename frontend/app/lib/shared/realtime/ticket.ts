/**
 * Fetching a websocket ticket.
 *
 * Its own module so `client.ts` stays transport-only and can be tested without
 * mocking the API layer: the client takes a `fetchTicket` callback, and this is
 * what the app passes in.
 *
 * Goes through `apiFetch`, which already carries the session cookie, attaches
 * the CSRF header this POST requires, and silently refreshes an aged-out access
 * token — so a ticket fetch 15 minutes into a session works rather than 401ing.
 */

import { apiFetch } from '$shared/api/client';

export interface RealtimeTicket {
  ticket: string;
  expires_at: string;
  expires_in_seconds: number;
}

/**
 * Mint a ticket. Call once per connection attempt, never cached.
 *
 * The ticket is single-use: the server burns its id on the handshake, so a
 * reconnect that reuses one is refused with `ticket_already_used`. That is why
 * this is wired as a callback the client invokes on every attempt rather than a
 * value held somewhere.
 */
export function fetchRealtimeTicket(): Promise<RealtimeTicket> {
  return apiFetch<RealtimeTicket>({ url: '/realtime/ticket', method: 'POST' });
}
