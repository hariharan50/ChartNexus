import { useEffect, useRef, useState } from 'react';

export type TickDirection = 'up' | 'down';

/**
 * Briefly mark rows whose value moved since the last update.
 *
 * A table of two hundred numbers refreshing on a timer is indistinguishable
 * from a static one — the eye has no way to tell which figures are new. A
 * short flash on the cells that actually changed is what makes a quote board
 * read as live.
 *
 * Deliberately *not* driven by a per-row animation: the flash is derived from
 * comparing two snapshots, so it costs one pass over the rows and no state per
 * row. Rows that vanish between updates drop out of the map on their own.
 *
 * The first render never flashes. Arriving at a page is not a price move, and
 * lighting up the whole table on load would teach people to ignore the colour.
 */
export function useTickFlash<T>(
  rows: T[],
  key: (row: T) => string,
  value: (row: T) => number | null,
  durationMs = 900
): ReadonlyMap<string, TickDirection> {
  const previous = useRef<Map<string, number> | null>(null);
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>());
  const [flashes, setFlashes] = useState<Map<string, TickDirection>>(new Map());

  useEffect(() => {
    const current = new Map<string, number>();
    for (const row of rows) {
      const next = value(row);
      if (next !== null) current.set(key(row), next);
    }

    const before = previous.current;
    previous.current = current;
    // First snapshot: record it, flash nothing.
    if (before === null) return;

    const changed = new Map<string, TickDirection>();
    for (const [id, next] of current) {
      const last = before.get(id);
      if (last === undefined || last === next) continue;
      changed.set(id, next > last ? 'up' : 'down');
    }
    if (changed.size === 0) return;

    setFlashes((prev) => new Map([...prev, ...changed]));

    for (const id of changed.keys()) {
      const existing = timers.current.get(id);
      if (existing) clearTimeout(existing);
      timers.current.set(
        id,
        setTimeout(() => {
          timers.current.delete(id);
          setFlashes((prev) => {
            if (!prev.has(id)) return prev;
            const next = new Map(prev);
            next.delete(id);
            return next;
          });
        }, durationMs)
      );
    }
  }, [rows, key, value, durationMs]);

  // Timers outlive the render that scheduled them, so they have to be cleared
  // on unmount or they fire setState against a gone component.
  useEffect(() => {
    const pending = timers.current;
    return () => {
      for (const timer of pending.values()) clearTimeout(timer);
      pending.clear();
    };
  }, []);

  return flashes;
}
