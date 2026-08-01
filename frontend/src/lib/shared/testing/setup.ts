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
