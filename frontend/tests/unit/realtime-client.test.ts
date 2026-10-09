import { beforeEach, describe, expect, it, vi } from 'vitest';
import {
  RealtimeClient,
  resolveWebsocketUrl,
  withTicket,
  type ConnectionState,
  type SocketLike
} from '../../app/lib/shared/realtime/client';

/**
 * The connection's reconnect behaviour, driven with a fake socket and a fake
 * clock so none of it depends on a browser or on real time.
 *
 * The property that matters most is a fresh ticket per attempt. Tickets are
 * single-use, so a reconnect loop that reused one would be refused forever —
 * and it would look like a server fault, not a client bug.
 */

class FakeSocket implements SocketLike {
  onopen: ((event: unknown) => void) | null = null;
  onclose: ((event: unknown) => void) | null = null;
  onerror: ((event: unknown) => void) | null = null;
  onmessage: ((event: { data: unknown }) => void) | null = null;

  sent: string[] = [];
  closedWith: number | undefined;

  constructor(readonly url: string) {}

  send(data: string): void {
    this.sent.push(data);
  }

  close(code?: number): void {
    this.closedWith = code;
  }

  /** Drive the lifecycle from the test's point of view. */
  open(): void {
    this.onopen?.({});
  }

  deliver(frame: unknown): void {
    this.onmessage?.({ data: typeof frame === 'string' ? frame : JSON.stringify(frame) });
  }

  drop(): void {
    this.onclose?.({});
  }

  messages(): unknown[] {
    return this.sent.map((raw) => JSON.parse(raw));
  }
}

interface Harness {
  client: RealtimeClient;
  sockets: FakeSocket[];
  states: ConnectionState[];
  frames: unknown[];
  tickets: string[];
  /** Run the next scheduled retry. */
  runPendingTimer: () => void;
  pendingDelays: number[];
  failTicket: (reason?: boolean) => void;
}

function harness(): Harness {
  const sockets: FakeSocket[] = [];
  const states: ConnectionState[] = [];
  const frames: unknown[] = [];
  const tickets: string[] = [];
  const timers: Array<{ fn: () => void; ms: number }> = [];
  const pendingDelays: number[] = [];
  let ticketFails = false;
  let issued = 0;

  const client = new RealtimeClient({
    url: '/ws',
    fetchTicket: async () => {
      if (ticketFails) throw new Error('no ticket');
      issued += 1;
      const ticket = `ticket-${issued}`;
      tickets.push(ticket);
      return ticket;
    },
    onFrame: (frame) => frames.push(frame),
    onState: (state) => states.push(state),
    createSocket: (url) => {
      const socket = new FakeSocket(url);
      sockets.push(socket);
      return socket;
    },
    schedule: (fn, ms) => {
      timers.push({ fn, ms });
      pendingDelays.push(ms);
      return timers.length;
    },
    cancel: (handle) => {
      const timer = timers[handle - 1];
      if (timer) timer.fn = () => {};
    },
    // Deterministic jitter: the midpoint of the 50–100% window.
    random: () => 0.5
  });

  return {
    client,
    sockets,
    states,
    frames,
    tickets,
    pendingDelays,
    runPendingTimer: () => {
      const timer = timers.shift();
      pendingDelays.shift();
      timer?.fn();
    },
    failTicket: (reason = true) => {
      ticketFails = reason;
    }
  };
}

/** Let the client's awaited ticket fetch settle. */
const settle = () => new Promise<void>((resolve) => setTimeout(resolve, 0));

describe('url handling', () => {
  it('resolves a same-origin path against the page', () => {
    expect(resolveWebsocketUrl('/ws', { protocol: 'http:', host: 'localhost:5173' })).toBe(
      'ws://localhost:5173/ws'
    );
  });

  it('uses wss on a secure page', () => {
    expect(resolveWebsocketUrl('/ws', { protocol: 'https:', host: 'chartnexus.example' })).toBe(
      'wss://chartnexus.example/ws'
    );
  });

  it('passes an absolute websocket url through untouched', () => {
    // compose.dev.yml sets one for the containerised frontend.
    expect(resolveWebsocketUrl('ws://localhost:8001/ws')).toBe('ws://localhost:8001/ws');
  });

  it('appends the ticket, preserving an existing query string', () => {
    expect(withTicket('ws://h/ws?v=1', 'abc')).toBe('ws://h/ws?v=1&ticket=abc');
    expect(withTicket('ws://h/ws', 'a b')).toBe('ws://h/ws?ticket=a%20b');
  });
});

describe('connecting', () => {
  let h: Harness;

  beforeEach(() => {
    h = harness();
  });

  it('fetches a ticket and puts it in the url', async () => {
    h.client.connect();
    await settle();

    expect(h.sockets).toHaveLength(1);
    expect(h.sockets[0]?.url).toContain('ticket=ticket-1');
  });

  it('reports open once the socket opens', async () => {
    h.client.connect();
    await settle();
    h.sockets[0]?.open();

    expect(h.states).toEqual(['connecting', 'open']);
  });

  it('a second connect while one is in flight does not open two sockets', async () => {
    h.client.connect();
    h.client.connect();
    await settle();

    expect(h.sockets).toHaveLength(1);
  });

  it('subscribes to the desired topics on open', async () => {
    h.client.setTopics(['snapshots:NIFTY']);
    h.client.connect();
    await settle();
    h.sockets[0]?.open();

    expect(h.sockets[0]?.messages()).toEqual([{ type: 'subscribe', topics: ['snapshots:NIFTY'] }]);
  });
});

describe('topics', () => {
  let h: Harness;

  beforeEach(async () => {
    h = harness();
    h.client.connect();
    await settle();
    h.sockets[0]?.open();
  });

  it('sends only what changed', () => {
    h.client.setTopics(['snapshots:NIFTY']);
    h.client.setTopics(['snapshots:NIFTY', 'snapshots:SENSEX']);

    expect(h.sockets[0]?.messages()).toEqual([
      { type: 'subscribe', topics: ['snapshots:NIFTY'] },
      { type: 'subscribe', topics: ['snapshots:SENSEX'] }
    ]);
  });

  it('unsubscribes what was dropped', () => {
    h.client.setTopics(['snapshots:NIFTY', 'snapshots:SENSEX']);
    h.client.setTopics(['snapshots:SENSEX']);

    expect(h.sockets[0]?.messages().at(-1)).toEqual({
      type: 'unsubscribe',
      topics: ['snapshots:NIFTY']
    });
  });

  it('an unchanged set sends nothing', () => {
    h.client.setTopics(['snapshots:NIFTY']);
    const before = h.sockets[0]?.sent.length ?? 0;

    h.client.setTopics(['snapshots:NIFTY']);

    expect(h.sockets[0]?.sent).toHaveLength(before);
  });
});

describe('reconnecting', () => {
  let h: Harness;

  beforeEach(() => {
    h = harness();
  });

  it('mints a NEW ticket for every attempt', async () => {
    // The whole reason the client holds a callback and never a ticket: a reused
    // single-use ticket is refused forever.
    h.client.connect();
    await settle();
    h.sockets[0]?.open();
    h.sockets[0]?.drop();

    h.runPendingTimer();
    await settle();

    expect(h.tickets).toEqual(['ticket-1', 'ticket-2']);
    expect(h.sockets[1]?.url).toContain('ticket=ticket-2');
  });

  it('resends the whole topic set after a drop', async () => {
    h.client.setTopics(['snapshots:NIFTY', 'snapshots:SENSEX']);
    h.client.connect();
    await settle();
    h.sockets[0]?.open();
    h.sockets[0]?.drop();

    h.runPendingTimer();
    await settle();
    h.sockets[1]?.open();

    // The server remembers nothing across a connection, so a delta would
    // silently leave the page unsubscribed.
    expect(h.sockets[1]?.messages()).toEqual([
      { type: 'subscribe', topics: ['snapshots:NIFTY', 'snapshots:SENSEX'] }
    ]);
  });

  it('backs off exponentially, and caps', async () => {
    h.client.connect();
    await settle();
    h.sockets[0]?.open();

    const delays: number[] = [];
    for (let attempt = 0; attempt < 8; attempt += 1) {
      h.sockets.at(-1)?.drop();
      delays.push(h.pendingDelays[0] ?? -1);
      h.runPendingTimer();
      await settle();
    }

    // 0.5 jitter on a 500ms base: 375, 750, 1500, … capped at 22500 (0.75 × 30s).
    expect(delays[0]).toBe(375);
    expect(delays[1]).toBe(750);
    expect(delays[2]).toBe(1500);
    expect(Math.max(...delays)).toBeLessThanOrEqual(22_500);
    // Monotonic until the cap.
    expect(delays[3]).toBeGreaterThan(delays[2] ?? 0);
  });

  it('resets the backoff after a successful open', async () => {
    h.client.connect();
    await settle();
    h.sockets[0]?.open();

    h.sockets[0]?.drop();
    h.runPendingTimer();
    await settle();
    h.sockets[1]?.open(); // recovered
    h.sockets[1]?.drop();

    // Back to the first step, not wherever the previous outage had climbed to.
    expect(h.pendingDelays[0]).toBe(375);
  });

  it('retries when the ticket fetch itself fails', async () => {
    h.failTicket();
    h.client.connect();
    await settle();

    expect(h.sockets).toHaveLength(0);
    expect(h.states).toContain('reconnecting');

    h.failTicket(false);
    h.runPendingTimer();
    await settle();

    expect(h.sockets).toHaveLength(1);
  });

  it('stops for good on an invalid session', async () => {
    h.client.connect();
    await settle();
    h.sockets[0]?.open();

    h.sockets[0]?.deliver({
      type: 'error',
      error: { code: 'not_authenticated', message: 'Authentication is required.' }
    });

    expect(h.states.at(-1)).toBe('offline');

    h.sockets[0]?.drop();
    expect(h.pendingDelays).toHaveLength(0);
  });

  it('keeps retrying after an expired ticket', async () => {
    // Recoverable: the next attempt mints a new one.
    h.client.connect();
    await settle();
    h.sockets[0]?.open();

    h.sockets[0]?.deliver({
      type: 'error',
      error: { code: 'ticket_expired', message: 'This connection ticket has expired.' }
    });
    h.sockets[0]?.drop();

    expect(h.pendingDelays).toHaveLength(1);
  });
});

describe('closing', () => {
  it('cancels a scheduled retry and reports idle', async () => {
    const h = harness();
    h.client.connect();
    await settle();
    h.sockets[0]?.open();
    h.sockets[0]?.drop();

    h.client.close();
    h.runPendingTimer();
    await settle();

    expect(h.sockets).toHaveLength(1);
    expect(h.states.at(-1)).toBe('idle');
  });

  it('closes the live socket', async () => {
    const h = harness();
    h.client.connect();
    await settle();
    h.sockets[0]?.open();

    h.client.close();

    expect(h.sockets[0]?.closedWith).toBe(1000);
  });

  it('a close during an in-flight ticket fetch does not open a socket', async () => {
    const h = harness();
    h.client.connect();
    h.client.close();
    await settle();

    expect(h.sockets).toHaveLength(0);
  });

  it('ignores a socket that throws on close', async () => {
    const h = harness();
    h.client.connect();
    await settle();
    const socket = h.sockets[0];
    if (socket)
      socket.close = vi.fn(() => {
        throw new Error('already closed');
      });

    expect(() => h.client.close()).not.toThrow();
  });
});

describe('frames', () => {
  it('forwards a parsed snapshot to the handler', async () => {
    const h = harness();
    h.client.connect();
    await settle();
    h.sockets[0]?.open();

    h.sockets[0]?.deliver({
      type: 'snapshot_committed',
      topic: 'snapshots:NIFTY',
      published_at: 'x',
      payload: {
        symbol: 'NIFTY',
        session_date: '2026-10-09',
        captured_at: 'x',
        source: 'mock'
      }
    });

    expect(h.frames).toHaveLength(1);
    expect(h.frames[0]).toMatchObject({ type: 'snapshot_committed' });
  });

  it('drops an unparseable frame without disturbing the connection', async () => {
    const h = harness();
    h.client.connect();
    await settle();
    h.sockets[0]?.open();

    h.sockets[0]?.deliver('not json at all');

    expect(h.frames).toHaveLength(0);
    expect(h.states.at(-1)).toBe('open');
  });
});
