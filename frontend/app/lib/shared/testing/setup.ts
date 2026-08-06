import '@testing-library/jest-dom/vitest';
import { afterEach, vi } from 'vitest';

/**
 * Loaded by vitest.config.ts before every unit and component test.
 */

// jsdom implements neither of these, and both are used by chart containers and
// virtualised tables.
class ResizeObserverStub {
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
}
vi.stubGlobal('ResizeObserver', ResizeObserverStub);

class IntersectionObserverStub {
  readonly root = null;
  readonly rootMargin = '';
  readonly thresholds: readonly number[] = [];
  observe(): void {}
  unobserve(): void {}
  disconnect(): void {}
  takeRecords(): [] {
    return [];
  }
}
vi.stubGlobal('IntersectionObserver', IntersectionObserverStub);

// Node 25 defines its own experimental `localStorage`/`sessionStorage` globals.
// They win over jsdom's inside the test environment, and without
// `--localstorage-file` what survives is a plain object with no `clear`, `key`
// or `length` — enough for `getItem`/`setItem` to look fine and for anything
// else to fail at runtime. The preference stores round-trip through Storage, so
// give them a real one.
class MemoryStorage implements Storage {
  #entries = new Map<string, string>();

  get length(): number {
    return this.#entries.size;
  }

  key(index: number): string | null {
    return [...this.#entries.keys()][index] ?? null;
  }

  getItem(key: string): string | null {
    return this.#entries.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.#entries.set(String(key), String(value));
  }

  removeItem(key: string): void {
    this.#entries.delete(key);
  }

  clear(): void {
    this.#entries.clear();
  }
}

vi.stubGlobal('localStorage', new MemoryStorage());
vi.stubGlobal('sessionStorage', new MemoryStorage());

vi.stubGlobal('matchMedia', (query: string) => ({
  matches: false,
  media: query,
  onchange: null,
  addEventListener: () => {},
  removeEventListener: () => {},
  dispatchEvent: () => false
}));

// Market data is timestamp-sensitive; a fixed clock keeps "stale" assertions
// from depending on when the suite runs. Individual tests override it.
afterEach(() => {
  vi.useRealTimers();
});
