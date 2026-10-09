/**
 * The websocket connection: ticket, connect, subscribe, reconnect.
 *
 * Plain class, not a hook — so the reconnect logic can be tested with a fake
 * socket and a fake clock instead of a browser. `use-realtime.ts` is the thin
 * React wrapper over it.
 *
 * **A fresh ticket every attempt.** Tickets are single-use: the server burns the
 * id on the handshake. A reconnect loop that reuses one gets
 * `ticket_already_used` forever — the single most likely way to get this wrong,
 * which is why the client holds a `fetchTicket` callback and never a ticket.
 *
 * **Topics are desired state, not commands.** The caller sets the set it wants;
 * this resends the whole set after every reconnect. The server accepts a full
 * resend (already-held topics are ignored) precisely so a client never has to
 * track what survived a drop.
 */

import {
  isFatalError,
  parseServerFrame,
  subscribeMessage,
  unsubscribeMessage,
  type ServerFrame,
  type Topic
} from './protocol';

export type ConnectionState =
  /** Never started, or deliberately closed. */
  | 'idle'
  /** First attempt in flight. */
  | 'connecting'
  /** Connected, and the server has welcomed us. */
  | 'open'
  /** Dropped; another attempt is scheduled. */
  | 'reconnecting'
  /** Given up — the session is not valid, so retrying cannot help. */
  | 'offline';

/** The parts of `WebSocket` this client uses, so a test can supply its own. */
export interface SocketLike {
  send(data: string): void;
  close(code?: number, reason?: string): void;
  onopen: ((event: unknown) => void) | null;
  onclose: ((event: unknown) => void) | null;
  onerror: ((event: unknown) => void) | null;
  onmessage: ((event: { data: unknown }) => void) | null;
}

export interface RealtimeClientOptions {
  /** Configured `PUBLIC_WS_URL`; relative or absolute. */
  url: string;
  /** Mints a ticket. Called once per attempt. */
  fetchTicket: () => Promise<string>;
  onFrame: (frame: ServerFrame) => void;
  onState: (state: ConnectionState) => void;
  /** Injected in tests. */
  createSocket?: (url: string) => SocketLike;
  schedule?: (fn: () => void, ms: number) => number;
  cancel?: (handle: number) => void;
  random?: () => number;
}

/** First backoff step. Short, because most drops are a blip. */
const BASE_DELAY_MS = 500;
/** Ceiling, so a long outage settles into a slow retry rather than a hammer. */
const MAX_DELAY_MS = 30_000;

export class RealtimeClient {
  private readonly options: RealtimeClientOptions;
  private readonly createSocket: (url: string) => SocketLike;
  private readonly schedule: (fn: () => void, ms: number) => number;
  private readonly cancel: (handle: number) => void;
  private readonly random: () => number;

  private socket: SocketLike | null = null;
  private state: ConnectionState = 'idle';
  private desired: Topic[] = [];
  private attempt = 0;
  private retryHandle: number | null = null;
  /** Set by `close()`, so an in-flight attempt does not resurrect the client. */
  private stopped = false;
  /** Guards against two attempts overlapping while a ticket fetch is pending. */
  private connecting = false;

  constructor(options: RealtimeClientOptions) {
    this.options = options;
    this.createSocket = options.createSocket ?? defaultCreateSocket;
    this.schedule = options.schedule ?? ((fn, ms) => setTimeout(fn, ms) as unknown as number);
    this.cancel = options.cancel ?? ((handle) => clearTimeout(handle));
    this.random = options.random ?? Math.random;
  }

  /** Begin connecting. Safe to call twice; the second is a no-op. */
  connect(): void {
    this.stopped = false;
    if (this.socket || this.connecting) return;
    void this.attemptConnection('connecting');
  }

  /** Close for good. Cancels any scheduled retry. */
  close(): void {
    this.stopped = true;
    this.clearRetry();
    const socket = this.socket;
    this.socket = null;
    if (socket) {
      socket.onopen = socket.onclose = socket.onerror = socket.onmessage = null;
      try {
        socket.close(1000, 'client closed');
      } catch {
        // Already closed, or closing. Nothing to recover.
      }
    }
    this.setState('idle');
  }

  /**
   * Replace the set of topics this connection wants.
   *
   * Sends only the difference while connected, and remembers the whole set for
   * the next reconnect. Called on every render that changes the focused symbol,
   * so it must be cheap and idempotent — an unchanged set sends nothing.
   */
  setTopics(topics: readonly Topic[]): void {
    const next = [...new Set(topics)].sort();
    const added = next.filter((topic) => !this.desired.includes(topic));
    const removed = this.desired.filter((topic) => !next.includes(topic));
    this.desired = next;

    if (this.state !== 'open' || !this.socket) return;
    if (added.length) this.send(subscribeMessage(added));
    if (removed.length) this.send(unsubscribeMessage(removed));
  }

  get currentState(): ConnectionState {
    return this.state;
  }

  private async attemptConnection(announce: ConnectionState): Promise<void> {
    this.connecting = true;
    this.setState(announce);

    let ticket: string;
    try {
      ticket = await this.options.fetchTicket();
    } catch {
      // Could not even get a ticket — the API is unreachable or the session
      // lapsed. Treated as a droppable failure, not fatal: a 401 here means the
      // REST layer is already handling the session, and if the network simply
      // blinked the next attempt succeeds.
      this.connecting = false;
      this.scheduleRetry();
      return;
    }

    if (this.stopped) {
      this.connecting = false;
      return;
    }

    let socket: SocketLike;
    try {
      socket = this.createSocket(withTicket(this.options.url, ticket));
    } catch {
      this.connecting = false;
      this.scheduleRetry();
      return;
    }

    this.socket = socket;
    this.connecting = false;

    socket.onopen = () => {
      this.attempt = 0;
      this.setState('open');
      // Resend the whole desired set: after a drop the server remembers nothing.
      if (this.desired.length) this.send(subscribeMessage(this.desired));
    };

    socket.onmessage = (event) => {
      const frame = parseServerFrame(event.data);
      if (!frame) return;

      if (frame.type === 'error' && isFatalError(frame.error.code)) {
        // The session is not valid. Retrying would loop against the same wall.
        this.stopped = true;
        this.clearRetry();
        this.setState('offline');
        this.options.onFrame(frame);
        return;
      }
      this.options.onFrame(frame);
    };

    socket.onerror = () => {
      // `onclose` always follows, and that is where the retry is scheduled.
      // Handling it here too would double-schedule.
    };

    socket.onclose = () => {
      this.socket = null;
      if (this.stopped) return;
      this.scheduleRetry();
    };
  }

  private send(message: string): void {
    try {
      this.socket?.send(message);
    } catch {
      // A socket that died between the state check and the send. `onclose` will
      // fire and the reconnect will resend the whole set anyway.
    }
  }

  private scheduleRetry(): void {
    if (this.stopped || this.retryHandle !== null) return;

    const delay = this.backoff();
    this.attempt += 1;
    this.setState('reconnecting');
    this.retryHandle = this.schedule(() => {
      this.retryHandle = null;
      if (this.stopped) return;
      void this.attemptConnection('reconnecting');
    }, delay);
  }

  /**
   * Exponential, capped, with jitter.
   *
   * The jitter matters more than it looks: without it, every browser that
   * dropped when the server restarted comes back at the same instant and
   * knocks it over again.
   */
  private backoff(): number {
    const exponential = Math.min(BASE_DELAY_MS * 2 ** this.attempt, MAX_DELAY_MS);
    return Math.round(exponential * (0.5 + this.random() * 0.5));
  }

  private clearRetry(): void {
    if (this.retryHandle !== null) {
      this.cancel(this.retryHandle);
      this.retryHandle = null;
    }
  }

  private setState(state: ConnectionState): void {
    if (this.state === state) return;
    this.state = state;
    this.options.onState(state);
  }
}

/**
 * Resolve the configured path to an absolute websocket URL.
 *
 * `PUBLIC_WS_URL` is `/ws` by default — same-origin, which the Vite dev server
 * proxies to port 8001 and which nginx proxies in production. An absolute
 * `ws://host/ws` is also accepted, because `compose.dev.yml` sets one for the
 * containerised frontend, where the socket is not behind the same origin.
 */
export function resolveWebsocketUrl(
  configured: string,
  location?: { protocol: string; host: string }
): string {
  if (/^wss?:\/\//i.test(configured)) return configured;

  const origin =
    location ??
    (typeof window === 'undefined'
      ? undefined
      : { protocol: window.location.protocol, host: window.location.host });
  if (!origin) return configured;

  const scheme = origin.protocol === 'https:' ? 'wss:' : 'ws:';
  const path = configured.startsWith('/') ? configured : `/${configured}`;
  return `${scheme}//${origin.host}${path}`;
}

/** Append the ticket, preserving any query string already on the URL. */
export function withTicket(url: string, ticket: string): string {
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}ticket=${encodeURIComponent(ticket)}`;
}

function defaultCreateSocket(url: string): SocketLike {
  return new WebSocket(url) as unknown as SocketLike;
}
