import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode
} from 'react';
import type { ConnectionState } from './client';
import { useRealtimeConnection } from './use-realtime';

/**
 * One socket for the terminal, subscribed to whatever the mounted pages want.
 *
 * The alternative — each page opening its own connection — would mean a
 * handshake and a ticket per page, a reconnect on every navigation, and several
 * sockets delivering the same NIFTY frame to the same cache.
 *
 * So the connection lives here and pages *declare* their symbols with
 * `useRealtimeSymbols`. Registrations are reference-counted: two panels both
 * showing NIFTY produce one subscription, and the subscription is dropped only
 * when the last of them unmounts. Without the counting, the first panel to
 * leave would unsubscribe the other one's stream.
 */

interface RealtimeContextValue {
  state: ConnectionState;
  lastEventAt: number | null;
  /** Register interest; the returned function releases it. */
  register: (symbols: readonly string[]) => () => void;
}

const RealtimeContext = createContext<RealtimeContextValue | null>(null);

export function RealtimeProvider({ children }: { children: ReactNode }) {
  // symbol -> how many mounted consumers want it.
  const counts = useRef(new Map<string, number>());
  const [symbols, setSymbols] = useState<readonly string[]>([]);

  const publish = useCallback(() => {
    setSymbols([...counts.current.keys()].sort());
  }, []);

  const register = useCallback(
    (requested: readonly string[]) => {
      for (const symbol of new Set(requested)) {
        counts.current.set(symbol, (counts.current.get(symbol) ?? 0) + 1);
      }
      publish();

      return () => {
        for (const symbol of new Set(requested)) {
          const next = (counts.current.get(symbol) ?? 1) - 1;
          if (next <= 0) counts.current.delete(symbol);
          else counts.current.set(symbol, next);
        }
        publish();
      };
    },
    [publish]
  );

  const connection = useRealtimeConnection(symbols);

  const value = useMemo<RealtimeContextValue>(
    () => ({ state: connection.state, lastEventAt: connection.lastEventAt, register }),
    [connection.state, connection.lastEventAt, register]
  );

  return <RealtimeContext.Provider value={value}>{children}</RealtimeContext.Provider>;
}

/**
 * The connection's state, for an indicator.
 *
 * Returns a safe default outside the provider rather than throwing: a component
 * rendered in isolation by a test or a story should not need the whole terminal
 * shell just to show a dot.
 */
export function useRealtimeStatus(): { state: ConnectionState; lastEventAt: number | null } {
  const context = useContext(RealtimeContext);
  if (!context) return { state: 'idle', lastEventAt: null };
  return { state: context.state, lastEventAt: context.lastEventAt };
}

/**
 * Declare the symbols this component needs live updates for.
 *
 * Pass what the page actually shows. Subscribing to more than that is not free:
 * every frame invalidates queries, and every invalidation is a refetch against
 * a broker quota.
 *
 * A no-op outside the provider, so a page can be unit-tested without it.
 */
export function useRealtimeSymbols(symbols: readonly string[]): void {
  const context = useContext(RealtimeContext);
  // Joined so a new array of the same symbols does not re-register every render.
  const key = useMemo(() => [...new Set(symbols)].sort().join(','), [symbols]);

  useEffect(() => {
    if (!context) return;
    if (!key) return;
    return context.register(key.split(','));
    // `context.register` is stable (useCallback with a stable dep), so keying on
    // the symbol list alone is what keeps this from re-registering per render.
  }, [key, context]);
}
