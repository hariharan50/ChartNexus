import { describe, expect, it } from 'vitest';
import {
  ALL_SNAPSHOTS,
  isFatalError,
  parseServerFrame,
  pingMessage,
  snapshotsTopic,
  subscribeMessage,
  unsubscribeMessage,
  type ErrorCode
} from '../../app/lib/shared/realtime/protocol';

/**
 * The browser half of the websocket wire format.
 *
 * What is pinned here is the tolerance: parsing returns `null` instead of
 * throwing, so a frame from a newer server cannot tear down a working
 * connection. And the one asymmetry that has money attached — an unrecognised
 * `source` is read as simulated, never as live.
 */

describe('client messages', () => {
  it('encodes a subscribe', () => {
    expect(JSON.parse(subscribeMessage(['snapshots:NIFTY']))).toEqual({
      type: 'subscribe',
      topics: ['snapshots:NIFTY']
    });
  });

  it('encodes an unsubscribe', () => {
    expect(JSON.parse(unsubscribeMessage(['snapshots:NIFTY'], 'r1'))).toEqual({
      type: 'unsubscribe',
      topics: ['snapshots:NIFTY'],
      id: 'r1'
    });
  });

  it('omits the correlation id when there is none', () => {
    expect(JSON.parse(pingMessage())).toEqual({ type: 'ping' });
  });

  it('builds topics the server grammar accepts', () => {
    expect(snapshotsTopic('BANKNIFTY')).toBe('snapshots:BANKNIFTY');
    expect(ALL_SNAPSHOTS).toBe('snapshots:*');
  });
});

describe('parsing server frames', () => {
  it('parses a welcome', () => {
    const frame = parseServerFrame(
      '{"type":"welcome","connection_id":"abc","protocol_version":1,"server_time":"2026-10-09T08:30:00Z"}'
    );

    expect(frame).toEqual({
      type: 'welcome',
      connection_id: 'abc',
      protocol_version: 1,
      server_time: '2026-10-09T08:30:00Z'
    });
  });

  it('parses an ack', () => {
    const frame = parseServerFrame('{"type":"ack","topics":["snapshots:NIFTY"],"id":"r1"}');

    expect(frame).toMatchObject({ type: 'ack', topics: ['snapshots:NIFTY'], id: 'r1' });
  });

  it('parses a snapshot, keeping spot as a string', () => {
    const frame = parseServerFrame(
      JSON.stringify({
        type: 'snapshot_committed',
        topic: 'snapshots:NIFTY',
        published_at: '2026-10-09T08:30:01Z',
        payload: {
          symbol: 'NIFTY',
          session_date: '2026-10-09',
          captured_at: '2026-10-09T08:30:00Z',
          source: 'live',
          spot: '24512.35',
          expiry: '2026-10-14'
        }
      })
    );

    expect(frame).toEqual({
      type: 'snapshot_committed',
      topic: 'snapshots:NIFTY',
      published_at: '2026-10-09T08:30:01Z',
      payload: {
        symbol: 'NIFTY',
        session_date: '2026-10-09',
        captured_at: '2026-10-09T08:30:00Z',
        source: 'live',
        spot: '24512.35',
        expiry: '2026-10-14'
      }
    });
  });

  it('reads a nullable spot as null, not as zero', () => {
    const frame = parseServerFrame(
      JSON.stringify({
        type: 'snapshot_committed',
        topic: 'snapshots:NIFTY',
        published_at: 'x',
        payload: {
          symbol: 'NIFTY',
          session_date: '2026-10-09',
          captured_at: 'x',
          source: 'mock',
          spot: null,
          expiry: null
        }
      })
    );

    expect(frame).toMatchObject({ payload: { spot: null, expiry: null } });
  });

  it('treats an unrecognised source as simulated', () => {
    // Mislabelling mock data as live is the one error with money attached.
    const frame = parseServerFrame(
      JSON.stringify({
        type: 'snapshot_committed',
        topic: 'snapshots:NIFTY',
        published_at: 'x',
        payload: {
          symbol: 'NIFTY',
          session_date: '2026-10-09',
          captured_at: 'x',
          source: 'something-new'
        }
      })
    );

    expect(frame).toMatchObject({ payload: { source: 'mock' } });
  });

  it('parses an error frame', () => {
    const frame = parseServerFrame(
      '{"type":"error","error":{"code":"unknown_topic","message":"Nope.","id":"r2"}}'
    );

    expect(frame).toEqual({
      type: 'error',
      error: { code: 'unknown_topic', message: 'Nope.', id: 'r2' }
    });
  });

  it.each([
    ['not a string', 42],
    ['malformed json', 'not json'],
    ['a json array', '[1,2,3]'],
    ['a bare string', '"hello"'],
    ['an unknown type', '{"type":"quotes"}'],
    ['no type at all', '{"topics":[]}'],
    ['a welcome without an id', '{"type":"welcome","protocol_version":1}'],
    ['a snapshot without a payload', '{"type":"snapshot_committed","topic":"snapshots:NIFTY"}'],
    [
      'a snapshot missing its symbol',
      '{"type":"snapshot_committed","topic":"t","payload":{"session_date":"d","captured_at":"c"}}'
    ],
    ['an error without a code', '{"type":"error","error":{"message":"x"}}']
  ])('returns null for %s rather than throwing', (_label, raw) => {
    expect(parseServerFrame(raw)).toBeNull();
  });
});

describe('error classification', () => {
  it('only an invalid session stops the client retrying', () => {
    expect(isFatalError('not_authenticated')).toBe(true);
  });

  it.each<ErrorCode>([
    'ticket_expired',
    'ticket_already_used',
    'malformed_frame',
    'unknown_topic',
    'topic_limit_exceeded',
    'internal_error',
    'unknown_message_type'
  ])('%s is recoverable, because every attempt mints a new ticket', (code) => {
    expect(isFatalError(code)).toBe(false);
  });
});
