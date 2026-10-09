/**
 * The React wrapper over `RealtimeClient`.
 *
 * One connection for the life of the terminal, held in a ref so a re-render
 * never opens a second socket. Topics follow the symbols the mounted pages
 * declare: switching the index tab sends a subscribe/unsubscribe pair rather
 * than reconnecting.
 *
 * This is the low-level engine. Pages do not call it — they call
 * `useRealtimeSymbols` from `RealtimeProvider`, which is what owns the registry
 * of who wants what. Calling this twice would open two sockets.
 *
 * Must run inside `QueryClientProvider`: it invalidates that cache.
 */

import { useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { PUBLIC_WS_URL } from '$shared/config/env';
import { RealtimeClient, resolveWebsocketUrl, type ConnectionState } from './client';
import { snapshotsTopic, type ServerFrame } from './protocol';
import { invalidateForSnapshot } from './query-cache-sync';
import { fetchRealtimeTicket } from './ticket';

export interface RealtimeConnection {
  state: ConnectionState;
  /** Epoch ms of the last data frame, for an "updated 3s ago" reading. */
  lastEventAt: number | null;
}

/**
 * Open one connection and keep it subscribed to `symbols`.
 *
 * An empty list is valid and normal: the socket stays open with no
 * subscriptions, so the first page that declares a symbol gets its stream
 * without waiting for a handshake.
 */
export function useRealtimeConnection(symbols: readonly string[]): RealtimeConnection {
  const queryClient = useQueryClient();
  const [state, setState] = useState<ConnectionState>('idle');
  const [lastEventAt, setLastEventAt] = useState<number | null>(null);
  const clientRef = useRef<RealtimeClient | null>(null);

  // Sorted and joined so a fresh array of the same symbols does not re-run the
  // effect — the common case, since callers build these lists inline.
  const topicKey = useMemo(() => [...new Set(symbols)].sort().join(','), [symbols]);

  // Held in a ref so the client is constructed once yet always calls the
  // current closure. Rebuilding the client to pick up a new handler would drop
  // the socket on every render.
  const onFrame = useRef<(frame: ServerFrame) => void>(() => {});
  onFrame.current = (frame: ServerFrame) => {
    if (frame.type !== 'snapshot_committed') return;
    setLastEventAt(Date.now());
    invalidateForSnapshot(queryClient, frame.payload);
  };

  useEffect(() => {
    // Effects do not run during SSR, which is what keeps this safe: there is no
    // `WebSocket` on the server and no session to mint a ticket against.
    const client = new RealtimeClient({
      url: resolveWebsocketUrl(PUBLIC_WS_URL),
      fetchTicket: async () => (await fetchRealtimeTicket()).ticket,
      onFrame: (frame) => onFrame.current(frame),
      onState: setState
    });
    clientRef.current = client;
    client.connect();

    return () => {
      client.close();
      clientRef.current = null;
    };
    // Deliberately empty. One connection for the life of the terminal; topic
    // changes go through `setTopics` in the effect below, not a reconnect.
  }, []);

  useEffect(() => {
    const topics = topicKey ? topicKey.split(',').map(snapshotsTopic) : [];
    clientRef.current?.setTopics(topics);
  }, [topicKey]);

  return { state, lastEventAt };
}
