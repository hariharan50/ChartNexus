import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import ExpiryPicker from '../../app/routes/terminal/future-lab/components/ExpiryPicker';

/**
 * The expiry listbox.
 *
 * It replaced a native `<select>`, which came with the platform's keyboard
 * behaviour for free. Owning the popup means owning that behaviour too, so
 * what is pinned here is the contract a `<select>` used to honour: arrows move,
 * Enter picks, Escape closes and hands focus back, and opening starts on the
 * row that is already selected.
 */

const EXPIRIES = {
  expiries: [
    { series: 0, expiry: '2026-09-29' },
    { series: 1, expiry: '2026-10-27' },
    { series: 2, expiry: '2026-11-23' }
  ]
};

beforeEach(() => {
  vi.useFakeTimers({ shouldAdvanceTime: true });
  vi.setSystemTime(new Date('2026-09-23T06:00:00Z'));
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(EXPIRIES), { status: 200 }))
  );
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function mount(ui: ReactElement) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } }
  });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

async function openList(onSeries = vi.fn()) {
  mount(<ExpiryPicker series={0} onSeries={onSeries} />);
  const trigger = await screen.findByRole('button', { name: 'Contract expiry' });
  await waitFor(() => expect(trigger).toHaveTextContent('29 Sep 2026'));
  await userEvent.click(trigger);
  return { trigger, list: await screen.findByRole('listbox'), onSeries };
}

describe('ExpiryPicker', () => {
  it('shows each contract with its countdown and its position', () => {
    /* Three aligned columns are the reason this is not a `<select>`: a native
       option can only carry one string. */
    return openList().then(async ({ list }) => {
      const options = within(list).getAllByRole('option');
      expect(options).toHaveLength(3);
      expect(options[0]).toHaveTextContent('29 Sep 2026');
      expect(options[0]).toHaveTextContent('6d');
      expect(options[0]).toHaveTextContent('Near month');
      expect(options[2]).toHaveTextContent('Far month');
    });
  });

  it('opens on the row already selected', async () => {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    render(
      <QueryClientProvider client={client}>
        <ExpiryPicker series={1} onSeries={vi.fn()} />
      </QueryClientProvider>
    );
    await userEvent.click(await screen.findByRole('button', { name: 'Contract expiry' }));

    const options = within(await screen.findByRole('listbox')).getAllByRole('option');
    expect(options[1]).toHaveAttribute('aria-selected', 'true');
    await waitFor(() => expect(options[1]).toHaveFocus());
  });

  it('moves with the arrows and picks with Enter', async () => {
    const { onSeries } = await openList();

    await userEvent.keyboard('{ArrowDown}{Enter}');
    expect(onSeries).toHaveBeenCalledWith(1);
  });

  it('closes on Escape and hands focus back to the trigger', async () => {
    const { trigger } = await openList();

    await userEvent.keyboard('{Escape}');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
  });

  it('picks on click', async () => {
    const { list, onSeries } = await openList();

    await userEvent.click(within(list).getAllByRole('option')[2]!);
    expect(onSeries).toHaveBeenCalledWith(2);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('closes when the pointer goes down outside it', async () => {
    await openList();

    await userEvent.click(document.body);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('says when the selected contract carries no open interest', () => {
    /* Empty build-up columns are a claim about the market unless the page says
       nothing measured them. */
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
    render(
      <QueryClientProvider client={client}>
        <ExpiryPicker series={2} onSeries={vi.fn()} hasOpenInterest={false} />
      </QueryClientProvider>
    );
    expect(screen.getByText('no OI')).toBeInTheDocument();
  });
});
