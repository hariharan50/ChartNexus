/**
 * Day-scoped, per-user persistence for the Hella chat.
 *
 * The console keeps a conversation alive across reloads and navigation for the
 * whole trading day. The transcript and the server `session_id` are mirrored to
 * `localStorage` so a reload rehydrates instantly; the server's own copy (keyed
 * by tenant) keeps the model's context and expires at the end of the IST day.
 *
 * Two isolation rules the key encodes, so one browser shared by two people never
 * crosses streams:
 *  - **Per user** — the key carries the signed-in user's id. A different user
 *    reads a different key even before logout clears anything.
 *  - **Per IST day** — a stored chat from a previous day is discarded on load,
 *    matching the server's end-of-day expiry.
 *
 * `clearAllChats()` wipes every stored chat on sign-out.
 */

import type { ChatMessage } from './types';

const PREFIX = 'mc.hella.chat.';

interface StoredChat {
  day: string;
  sessionId: string | null;
  messages: ChatMessage[];
}

export interface LoadedChat {
  sessionId: string | null;
  messages: ChatMessage[];
}

const EMPTY: LoadedChat = { sessionId: null, messages: [] };

/** Today's date in IST as `YYYY-MM-DD` — the reset boundary. */
function istDay(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Kolkata' }).format(new Date());
}

function keyFor(userId: string, symbol: string): string {
  return `${PREFIX}${userId}.${symbol}`;
}

/** Drop any in-flight flags — a chat reloaded mid-stream must render as settled. */
function settle(messages: ChatMessage[]): ChatMessage[] {
  return messages.map((msg) => (msg.streaming ? { ...msg, streaming: false } : msg));
}

export function loadChat(userId: string, symbol: string): LoadedChat {
  if (typeof window === 'undefined' || !userId) return EMPTY;
  const key = keyFor(userId, symbol);
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return EMPTY;
    const stored = JSON.parse(raw) as StoredChat;
    if (stored.day !== istDay()) {
      window.localStorage.removeItem(key);
      return EMPTY;
    }
    const messages = Array.isArray(stored.messages) ? settle(stored.messages) : [];
    return { sessionId: stored.sessionId ?? null, messages };
  } catch {
    return EMPTY;
  }
}

export function saveChat(
  userId: string,
  symbol: string,
  sessionId: string | null,
  messages: ChatMessage[]
): void {
  if (typeof window === 'undefined' || !userId) return;
  try {
    const payload: StoredChat = { day: istDay(), sessionId, messages: settle(messages) };
    window.localStorage.setItem(keyFor(userId, symbol), JSON.stringify(payload));
  } catch {
    // Storage full or disabled — the chat simply won't survive a reload.
  }
}

/** Remove every stored Hella chat — called on sign-out. */
export function clearAllChats(): void {
  if (typeof window === 'undefined') return;
  try {
    const keys: string[] = [];
    for (let i = 0; i < window.localStorage.length; i += 1) {
      const key = window.localStorage.key(i);
      if (key && key.startsWith(PREFIX)) keys.push(key);
    }
    keys.forEach((key) => window.localStorage.removeItem(key));
  } catch {
    // Ignore — nothing we can do if storage is unavailable.
  }
}
