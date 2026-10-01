import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactElement } from 'react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import ExpiryPicker, {
  expiryLabel
} from '../../app/routes/terminal/options/components/ExpiryPicker';

/**
 * The Options Lab expiry control.
 *
 * The bug this replaced was not a styling problem: every tool rendered a `div`
 * that printed the nearest expiry and could not be changed, so picking another
 * expiry silently redrew the same chart. The cases below pin the three things
 * that made it broken — that the list is real, that choosing an entry reports
 * the chosen date, and that a far expiry says why its intraday history is thin
 * instead of just looking empty.
 */
vi.mock('../../app/lib/contexts/broker-connections/api', () => ({
  getExpiries: vi.fn(async () => ({
    instrument: 'NIFTY',
    expiries: ['2026-09-29', '2026-10-06', '2026-10-13'],
    provenance: { source: 'mock', fetched_at: '', age_seconds: 0, is_stale: true }
  }))
}));

function renderPicker(element: ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{element}</QueryClientProvider>);
}

afterEach(() => vi.useRealTimers());

describe('expiryLabel', () => {
  it('names the date and how long it has left', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-24T04:00:00Z'));

    expect(expiryLabel('2026-09-29')).toBe('29 Sep 2026 (5d)');
    expect(expiryLabel('2026-11-03')).toBe('3 Nov 2026 (40d)');
  });

  it('calls an unresolved expiry the nearest one rather than printing null', () => {
    expect(expiryLabel(null)).toBe('Nearest expiry');
  });
});

/** The list only exists once it is open — this is a listbox, not a `<select>`. */
async function openList() {
  const trigger = screen.getByRole('button', { name: 'Expiry' });
  await waitFor(() => expect(trigger).toBeEnabled());
  await userEvent.click(trigger);
  return screen.getAllByRole('option');
}

describe('ExpiryPicker', () => {
  it('lists every listed expiry, not just the nearest', async () => {
    renderPicker(
      <ExpiryPicker
        instrument="NIFTY"
        value={undefined}
        onChange={() => {}}
        resolved="2026-09-29"
      />
    );

    expect(await openList()).toHaveLength(4);
  });

  it('reports the expiry that was chosen', async () => {
    const onChange = vi.fn();
    renderPicker(
      <ExpiryPicker
        instrument="NIFTY"
        value={undefined}
        onChange={onChange}
        resolved="2026-09-29"
      />
    );

    const options = await openList();
    await userEvent.click(options[3]!);

    expect(onChange).toHaveBeenCalledWith('2026-10-13');
  });

  it('reports undefined when the default is chosen, so the backend picks', async () => {
    const onChange = vi.fn();
    renderPicker(
      <ExpiryPicker
        instrument="NIFTY"
        value="2026-10-13"
        onChange={onChange}
        resolved="2026-10-13"
      />
    );

    const options = await openList();
    await userEvent.click(options[0]!);

    expect(onChange).toHaveBeenCalledWith(undefined);
  });

  it('ticks the expiry that is selected', async () => {
    renderPicker(
      <ExpiryPicker
        instrument="NIFTY"
        value="2026-10-06"
        onChange={() => {}}
        resolved="2026-10-06"
      />
    );

    const options = await openList();
    const selected = options.filter((option) => option.getAttribute('aria-selected') === 'true');
    expect(selected).toHaveLength(1);
    expect(selected[0]).toHaveTextContent('6 Oct 2026');
  });

  it('warns when the answer that came back really was degraded', async () => {
    renderPicker(
      <ExpiryPicker
        instrument="NIFTY"
        value="2026-10-13"
        onChange={() => {}}
        resolved="2026-10-13"
        archiveBound
        dataQuality="live_proxy"
      />
    );

    await waitFor(() =>
      expect(screen.getByText(/archive holds the nearest expiry only/)).toBeInTheDocument()
    );
  });

  it('stays quiet when the picked expiry did come back with a full session', async () => {
    // Driven by the tier, not by the date's position in the list: after a
    // settlement the archived expiry is no longer the first entry, and
    // inferring it kept the control silent on exactly the degraded reads it
    // exists to explain.
    renderPicker(
      <ExpiryPicker
        instrument="NIFTY"
        value="2026-10-13"
        onChange={() => {}}
        resolved="2026-10-13"
        archiveBound
        dataQuality="intraday"
      />
    );
    await openList();

    expect(screen.queryByText(/archive holds/)).not.toBeInTheDocument();
  });

  it('says nothing while sitting on the backend-picked default', async () => {
    renderPicker(
      <ExpiryPicker
        instrument="NIFTY"
        value={undefined}
        onChange={() => {}}
        resolved="2026-09-29"
        archiveBound
        dataQuality="live_proxy"
      />
    );
    await openList();

    expect(screen.queryByText(/archive holds/)).not.toBeInTheDocument();
  });

  it('says nothing about the archive on a page that does not read it', async () => {
    renderPicker(
      <ExpiryPicker
        instrument="NIFTY"
        value="2026-10-13"
        onChange={() => {}}
        resolved="2026-10-13"
        dataQuality="live_proxy"
      />
    );
    await openList();

    expect(screen.queryByText(/archive holds/)).not.toBeInTheDocument();
  });

  it('hides its caption when the toolbar already prints one', async () => {
    const { rerender } = renderPicker(
      <ExpiryPicker instrument="NIFTY" value={undefined} onChange={() => {}} resolved={null} />
    );
    expect(screen.getByText('Expiry', { selector: 'p' })).toBeInTheDocument();

    rerender(
      <QueryClientProvider client={new QueryClient()}>
        <ExpiryPicker
          instrument="NIFTY"
          value={undefined}
          onChange={() => {}}
          resolved={null}
          hideLabel
        />
      </QueryClientProvider>
    );
    expect(screen.queryByText('Expiry', { selector: 'p' })).not.toBeInTheDocument();
  });
});
