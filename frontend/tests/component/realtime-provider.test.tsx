import { QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

/**
 * The symbol registry behind the single terminal connection.
 *
 * Reference counting is the point. Two panels both showing NIFTY must produce
 * one subscription, and — the bug this guards — the first of them to unmount
 * must not unsubscribe the other one's stream. That failure is silent: the
 * remaining panel just stops updating, and only the polled refetch hides it.
 *
 * The connection itself is stubbed. What is under test is which topics the
 * registry asks for, not the socket, which `realtime-client.test.ts` covers.
 */

const connections: Array<readonly string[]> = [];

vi.mock('../../app/lib/shared/realtime/use-realtime', () => ({
  useRealtimeConnection: (symbols: readonly string[]) => {
    connections.push([...symbols]);
    return { state: 'open' as const, lastEventAt: null };
  }
}));

const { RealtimeProvider, useRealtimeStatus, useRealtimeSymbols } =
  await import('../../app/lib/shared/realtime/RealtimeProvider');
const { createQueryClient } = await import('../../app/lib/shared/api/query-client');

/** The symbol set the connection was last asked for. */
const latest = (): readonly string[] => connections.at(-1) ?? [];

function Panel({ symbols }: { symbols: string[] }) {
  useRealtimeSymbols(symbols);
  return null;
}

function StatusLabel() {
  const { state } = useRealtimeStatus();
  return <span data-testid="state">{state}</span>;
}

function wrap(children: React.ReactNode) {
  return (
    <QueryClientProvider client={createQueryClient()}>
      <RealtimeProvider>{children}</RealtimeProvider>
    </QueryClientProvider>
  );
}

beforeEach(() => {
  connections.length = 0;
});

describe('RealtimeProvider', () => {
  it('asks for nothing when no page has declared a symbol', () => {
    render(wrap(<StatusLabel />));

    expect(latest()).toEqual([]);
  });

  it('collects the symbols a page declares', async () => {
    render(wrap(<Panel symbols={['NIFTY', 'SENSEX']} />));

    await waitFor(() => expect(latest()).toEqual(['NIFTY', 'SENSEX']));
  });

  it('merges two pages into one subscription set', async () => {
    render(
      wrap(
        <>
          <Panel symbols={['NIFTY']} />
          <Panel symbols={['BANKNIFTY']} />
        </>
      )
    );

    await waitFor(() => expect(latest()).toEqual(['BANKNIFTY', 'NIFTY']));
  });

  it('deduplicates a symbol two panels both want', async () => {
    render(
      wrap(
        <>
          <Panel symbols={['NIFTY']} />
          <Panel symbols={['NIFTY']} />
        </>
      )
    );

    await waitFor(() => expect(latest()).toEqual(['NIFTY']));
  });

  it('keeps a shared symbol when only one of its holders unmounts', async () => {
    // The silent bug: without reference counting, the first unmount would
    // unsubscribe the panel still on screen.
    const { rerender } = render(
      wrap(
        <>
          <Panel symbols={['NIFTY']} />
          <Panel symbols={['NIFTY']} />
        </>
      )
    );
    await waitFor(() => expect(latest()).toEqual(['NIFTY']));

    rerender(wrap(<Panel symbols={['NIFTY']} />));

    await waitFor(() => expect(latest()).toEqual(['NIFTY']));
  });

  it('drops a symbol once its last holder unmounts', async () => {
    const { rerender } = render(
      wrap(
        <>
          <Panel symbols={['NIFTY']} />
          <Panel symbols={['BANKNIFTY']} />
        </>
      )
    );
    await waitFor(() => expect(latest()).toEqual(['BANKNIFTY', 'NIFTY']));

    rerender(wrap(<Panel symbols={['NIFTY']} />));

    await waitFor(() => expect(latest()).toEqual(['NIFTY']));
  });

  it('swaps the subscription when a page changes its focused symbol', async () => {
    const { rerender } = render(wrap(<Panel symbols={['NIFTY']} />));
    await waitFor(() => expect(latest()).toEqual(['NIFTY']));

    rerender(wrap(<Panel symbols={['SENSEX']} />));

    await waitFor(() => expect(latest()).toEqual(['SENSEX']));
  });

  it('exposes the connection state to an indicator', () => {
    render(wrap(<StatusLabel />));

    expect(screen.getByTestId('state')).toHaveTextContent('open');
  });
});

describe('outside the provider', () => {
  it('useRealtimeStatus reports idle rather than throwing', () => {
    // So a component can be rendered by a test without the terminal shell.
    render(<StatusLabel />);

    expect(screen.getByTestId('state')).toHaveTextContent('idle');
  });

  it('useRealtimeSymbols is a no-op rather than throwing', () => {
    expect(() => render(<Panel symbols={['NIFTY']} />)).not.toThrow();
  });
});
