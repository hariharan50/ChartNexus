/**
 * The websocket wire format, browser side.
 *
 * The authority is `contracts/websocket/v1/*.schema.json`; this is the
 * TypeScript half of it, mirroring `backend/.../transport/websocket/protocol.py`.
 * Both directions live in one file so a server field no client reads — or the
 * reverse — is visible in a single diff.
 *
 * Parsing is total: `parseServerFrame` returns `null` rather than throwing. A
 * frame this build does not understand is a newer server, not a reason to tear
 * down a working connection and reconnect into the same wall.
 */

/** Bumped only for a breaking change; announced in `welcome`. */
export const PROTOCOL_VERSION = 1;

/** `snapshots:NIFTY`, or `snapshots:*` for every symbol. */
export type Topic = string;

export const SNAPSHOTS = 'snapshots';

/** Mirrors the enum in `contracts/websocket/v1/error.schema.json`. */
export type ErrorCode =
  | 'malformed_frame'
  | 'unknown_message_type'
  | 'unknown_topic'
  | 'topic_limit_exceeded'
  | 'not_authenticated'
  | 'ticket_expired'
  | 'ticket_already_used'
  | 'internal_error';

export interface WelcomeFrame {
  type: 'welcome';
  connection_id: string;
  protocol_version: number;
  server_time: string;
}

export interface AckFrame {
  type: 'ack';
  topics: string[];
  id?: string | undefined;
}

export interface SnapshotPayload {
  symbol: string;
  session_date: string;
  captured_at: string;
  /** `mock` must be badged, never presented as the market. */
  source: 'live' | 'mock';
  /** A decimal string, not a number — JSON numbers are doubles. */
  spot: string | null;
  expiry: string | null;
}

export interface SnapshotCommittedFrame {
  type: 'snapshot_committed';
  /** Always the concrete `snapshots:<SYMBOL>`, even for a wildcard subscriber. */
  topic: string;
  published_at: string;
  payload: SnapshotPayload;
}

export interface PongFrame {
  type: 'pong';
  server_time: string;
  id?: string | undefined;
}

export interface ErrorFrame {
  type: 'error';
  error: { code: ErrorCode; message: string; id?: string | undefined };
}

export type ServerFrame = WelcomeFrame | AckFrame | SnapshotCommittedFrame | PongFrame | ErrorFrame;

/** The topic an event about `symbol` is delivered as. */
export function snapshotsTopic(symbol: string): Topic {
  return `${SNAPSHOTS}:${symbol}`;
}

/** Every symbol on the snapshots stream. */
export const ALL_SNAPSHOTS: Topic = `${SNAPSHOTS}:*`;

// --------------------------------------------------------------------------
// Client to server
// --------------------------------------------------------------------------

export function subscribeMessage(topics: readonly Topic[], id?: string): string {
  return encode({ type: 'subscribe', topics: [...topics] }, id);
}

export function unsubscribeMessage(topics: readonly Topic[], id?: string): string {
  return encode({ type: 'unsubscribe', topics: [...topics] }, id);
}

export function pingMessage(id?: string): string {
  return encode({ type: 'ping' }, id);
}

function encode(body: Record<string, unknown>, id?: string): string {
  return JSON.stringify(id === undefined ? body : { ...body, id });
}

// --------------------------------------------------------------------------
// Server to client
// --------------------------------------------------------------------------

/**
 * Parse one server frame, or `null` if it is not one this build handles.
 *
 * Validates only the fields the client actually reads. A stricter check would
 * reject a server that added an optional field, which is exactly the
 * compatible change the protocol version exists to allow.
 */
export function parseServerFrame(raw: unknown): ServerFrame | null {
  if (typeof raw !== 'string') return null;

  let body: unknown;
  try {
    body = JSON.parse(raw);
  } catch {
    return null;
  }
  if (!isRecord(body)) return null;

  switch (body.type) {
    case 'welcome':
      return isString(body.connection_id) && isNumber(body.protocol_version)
        ? {
            type: 'welcome',
            connection_id: body.connection_id,
            protocol_version: body.protocol_version,
            server_time: asString(body.server_time)
          }
        : null;

    case 'ack':
      return Array.isArray(body.topics)
        ? { type: 'ack', topics: body.topics.filter(isString), id: optionalString(body.id) }
        : null;

    case 'snapshot_committed':
      return parseSnapshot(body);

    case 'pong':
      return { type: 'pong', server_time: asString(body.server_time), id: optionalString(body.id) };

    case 'error':
      return parseError(body);

    default:
      return null;
  }
}

function parseSnapshot(body: Record<string, unknown>): SnapshotCommittedFrame | null {
  const payload = body.payload;
  if (!isString(body.topic) || !isRecord(payload)) return null;
  if (!isString(payload.symbol) || !isString(payload.session_date)) return null;
  if (!isString(payload.captured_at)) return null;

  return {
    type: 'snapshot_committed',
    topic: body.topic,
    published_at: asString(body.published_at),
    payload: {
      symbol: payload.symbol,
      session_date: payload.session_date,
      captured_at: payload.captured_at,
      // Anything unexpected is treated as simulated. Mislabelling mock data as
      // live is the one error with money attached; the reverse is only cautious.
      source: payload.source === 'live' ? 'live' : 'mock',
      spot: isString(payload.spot) ? payload.spot : null,
      expiry: isString(payload.expiry) ? payload.expiry : null
    }
  };
}

function parseError(body: Record<string, unknown>): ErrorFrame | null {
  const error = body.error;
  if (!isRecord(error) || !isString(error.code)) return null;
  return {
    type: 'error',
    error: {
      code: error.code as ErrorCode,
      message: isString(error.message) ? error.message : 'The connection reported an error.',
      id: optionalString(error.id)
    }
  };
}

/**
 * Does this refusal mean "stop trying"?
 *
 * Only `not_authenticated` does: the session itself is not good, and
 * reconnecting cannot fix it — the REST layer's 401 handling owns that recovery.
 * `ticket_expired` and `ticket_already_used` are both cured by the next attempt,
 * because every attempt mints a new ticket.
 */
export function isFatalError(code: ErrorCode): boolean {
  return code === 'not_authenticated';
}

/** Is this refusal about the credential rather than the message we sent? */
export function isHandshakeError(code: ErrorCode): boolean {
  return (
    code === 'not_authenticated' || code === 'ticket_expired' || code === 'ticket_already_used'
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === 'string';
}

function isNumber(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value);
}

function asString(value: unknown): string {
  return isString(value) ? value : '';
}

function optionalString(value: unknown): string | undefined {
  return isString(value) ? value : undefined;
}
