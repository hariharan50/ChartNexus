import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor, within } from '@testing-library/react';
import { createRoutesStub } from 'react-router';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type * as TradeBuddyData from '../../app/routes/terminal/tools/trade-buddy/trade-buddy-data';
import { useInstrumentStore } from '../../app/lib/shared/ui/instrument-store';

/**
 * The Trade Buddy page, rendered against mocked endpoints.
 *
 * The unit suite pins the decision helpers; this pins that the page actually
 * *shows* what they decide. The things that matter most are all asserted here:
 * the feed verdict is stated in words and not just as a coloured dot, a level
 * that has flipped role says so, stale levels can be armed for today in one
 * click, and the six prices appear exactly once — editable, in the row that
 * reports their state.
 */

const getLevels = vi.fn();
const getEngineState = vi.fn();
const setLevels = vi.fn();
const clearLevels = vi.fn();
const fireTestAlert = vi.fn();
const getWatchlist = vi.fn();
const getSettings = vi.fn();
const setSettings = vi.fn();
const getChannels = vi.fn();
const getAlerts = vi.fn();

vi.mock('../../app/routes/terminal/tools/trade-buddy/trade-buddy-data', async () => {
  const actual = await vi.importActual<typeof TradeBuddyData>(
    '../../app/routes/terminal/tools/trade-buddy/trade-buddy-data'
  );
  return {
    ...actual,
    getLevels: (...args: unknown[]) => getLevels(...args),
    getEngineState: (...args: unknown[]) => getEngineState(...args),
    setLevels: (...args: unknown[]) => setLevels(...args),
    clearLevels: (...args: unknown[]) => clearLevels(...args),
    fireTestAlert: (...args: unknown[]) => fireTestAlert(...args),
    getWatchlist: (...args: unknown[]) => getWatchlist(...args),
    getSettings: (...args: unknown[]) => getSettings(...args),
    setSettings: (...args: unknown[]) => setSettings(...args),
    getChannels: (...args: unknown[]) => getChannels(...args),
    getAlerts: (...args: unknown[]) => getAlerts(...args)
  };
});

const TradeBuddy = (await import('../../app/routes/terminal/tools/trade-buddy/route')).default;

/** A tick that just arrived, relative to the real clock. */
function tickAt(secondsAgo: number): string {
  return new Date(Date.now() - secondsAgo * 1000).toISOString();
}

const BANDS = {
  touch: 6,
  approach: 25,
  break_buffer: 12,
  confirm_hold_seconds: 20,
  source: 'atr',
  atr: 200,
  note: null
};

const UNSCALED = { ...BANDS, source: 'points', atr: null };

function state(over: Record<string, unknown> = {}) {
  return {
    symbol: 'NIFTY',
    bands: BANDS,
    marked_on: '2026-11-02',
    levels_stale: false,
    market_open: true,
    last_tick_at: tickAt(2),
    last_price: 24_650,
    whatsapp_used: 2,
    whatsapp_limit: 20,
    levels: [
      {
        label: 'R1',
        level_price: 24_700,
        role: 'resistance',
        state: 'touched',
        break_pending: false,
        alerts_remaining: 2
      },
      {
        label: 'S1',
        level_price: 24_600,
        role: 'support',
        state: 'idle',
        break_pending: false,
        alerts_remaining: 3
      }
    ],
    ...over
  };
}

function settings(over: Record<string, unknown> = {}) {
  return {
    symbol: 'NIFTY',
    bands: BANDS,
    cooldown_minutes: 20,
    daily_alert_cap: 3,
    defaults: {
      touch_multiple: 0.03,
      approach_multiple: 0.125,
      break_multiple: 0.06,
      atr_period: 14,
      confirm_hold_seconds: 20,
      cooldown_minutes: 20,
      daily_alert_cap: 3,
      fallback_touch: 6,
      fallback_approach: 25,
      fallback_break_buffer: 12
    },
    overrides: {
      touch: null,
      approach: null,
      break_buffer: null,
      confirm_hold_seconds: null,
      cooldown_minutes: null,
      daily_alert_cap: null
    },
    ...over
  };
}

function channels(over: Record<string, unknown> = {}) {
  return {
    channels: [
      {
        channel: 'telegram',
        configured: true,
        ready: true,
        verified: true,
        enabled: true,
        label: '@my_alerts_bot',
        target: '12345',
        masked_secret: '8123******AAH1',
        ...over
      }
    ]
  };
}

function alert(over: Record<string, unknown> = {}) {
  return {
    kind: 'touched',
    label: 'R1',
    level_price: 24_700,
    price: 24_703,
    role_before: 'resistance',
    role_after: 'resistance',
    at: tickAt(600),
    channels: ['telegram'],
    ...over
  };
}

function watchlist(over: Record<string, unknown>[] = []) {
  const base = [
    { symbol: 'NIFTY', last_price: 24_650, nearest_label: 'R1', nearest_distance: 50 },
    { symbol: 'BANKNIFTY', last_price: 52_000, nearest_label: 'R1', nearest_distance: 120 },
    { symbol: 'SENSEX', last_price: 81_000, nearest_label: null, nearest_distance: null }
  ];
  return {
    instruments: base.map((row, i) => ({
      watched: row.symbol !== 'SENSEX',
      market_open: true,
      last_tick_at: tickAt(2),
      levels_marked: row.symbol === 'SENSEX' ? 0 : 6,
      attention: null,
      band_source: 'atr',
      ...row,
      ...(over[i] ?? {})
    }))
  };
}

/**
 * A Router is required, not incidental: the page reads the terminal-wide
 * instrument selection through `useSelectedInstrument`, which is backed by the
 * URL so a choice survives navigation between tools.
 */
function renderPage(initial = '/tools/trade-buddy') {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Stub = createRoutesStub([
    {
      path: '/tools/trade-buddy',
      Component: () => (
        <QueryClientProvider client={client}>
          <TradeBuddy />
        </QueryClientProvider>
      )
    }
  ]);
  return render(<Stub initialEntries={[initial]} />);
}

/** The levels table, once it has the saved marks in it. */
async function levelsTable() {
  const table = await screen.findByRole('table');
  await waitFor(() => expect(screen.getByLabelText('R1 price')).toHaveValue(24_700));
  return table;
}

beforeEach(() => {
  vi.clearAllMocks();
  // `useSelectedInstrument` remembers the choice so it follows you between
  // tools — in localStorage *and* in a module-level zustand store. Left in
  // place it also follows one test into the next, and a case that clicked
  // BANKNIFTY would silently change the instrument a later case asserts on.
  // Clearing storage alone is not enough; the singleton holds its own copy.
  localStorage.clear();
  useInstrumentStore.setState({ symbol: 'NIFTY' });
  getLevels.mockResolvedValue({
    symbol: 'NIFTY',
    levels: [
      { label: 'R1', price: 24_700, role: 'resistance' },
      { label: 'S1', price: 24_600, role: 'support' }
    ],
    marked_on: '2026-11-02'
  });
  getEngineState.mockResolvedValue(state());
  getWatchlist.mockResolvedValue(watchlist());
  getSettings.mockResolvedValue(settings());
  getChannels.mockResolvedValue(channels());
  getAlerts.mockResolvedValue({ symbol: 'NIFTY', session: '2026-11-02', alerts: [] });
});

describe('the page shell', () => {
  it('names itself and offers the six fixed slots', async () => {
    renderPage();

    expect(await screen.findByRole('heading', { name: 'Trade Buddy' })).toBeInTheDocument();
    for (const label of ['R3', 'R2', 'R1', 'S1', 'S2', 'S3']) {
      expect(screen.getByLabelText(`${label} price`)).toBeInTheDocument();
    }
  });

  it('seeds the inputs from the saved marks', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByLabelText('R1 price')).toHaveValue(24_700));
    expect(screen.getByLabelText('R2 price')).toHaveValue(null);
  });

  it('shows the six prices exactly once each', async () => {
    // The whole point of the merge: a form, a ladder and a table used to
    // render the same numbers three times over.
    renderPage();
    await levelsTable();

    expect(screen.getAllByLabelText('R1 price')).toHaveLength(1);
  });
});

describe('the feed verdict', () => {
  it('states "Live" in words, not only as a colour', async () => {
    renderPage();
    const card = await screen.findByRole('region', { name: /watcher status/i });
    expect(await within(card).findByText('Live')).toBeInTheDocument();
  });

  it('counts the tick age once it is live, which is what ages into a warning', async () => {
    renderPage();
    const card = await screen.findByRole('region', { name: /watcher status/i });
    expect(await within(card).findByText(/Last tick .* IST · \d+s ago/)).toBeInTheDocument();
  });

  it('says the market is closed rather than showing a stale tick', async () => {
    getEngineState.mockResolvedValue(state({ market_open: false }));
    renderPage();
    expect(await screen.findByText('Market closed')).toBeInTheDocument();
  });

  it('calls out a stale feed during market hours', async () => {
    // The distinction the feature rests on: this is a dead watcher, not a
    // quiet market, and the page has to say which.
    getEngineState.mockResolvedValue(state({ last_tick_at: tickAt(200) }));
    renderPage();
    expect(await screen.findByText('Feed stale')).toBeInTheDocument();
  });
});

describe('the levels card header', () => {
  it('shows the last price where the levels are', async () => {
    renderPage();
    // Twice, both inside the levels card and both deliberate: the big LTP in
    // the header, and the divider that puts price in the table's own order.
    expect(await screen.findAllByText('24,650.00')).toHaveLength(2);
  });

  it('confirms the session the levels are armed for', async () => {
    renderPage();
    expect(await screen.findByText('Armed for Mon 2 Nov')).toBeInTheDocument();
  });

  it('drops the confirmation once they go stale', async () => {
    getEngineState.mockResolvedValue(state({ marked_on: '2026-10-30', levels_stale: true }));
    renderPage();

    await screen.findByRole('status', { name: /stale levels/i });
    expect(screen.queryByText(/^Armed for/)).not.toBeInTheDocument();
  });

  it('calls out a level inside the approach band, and not one outside it', async () => {
    // R1 is 50 points away against a 25-point approach band, so there is
    // nothing to watch yet; a permanent callout would be furniture.
    renderPage();
    await levelsTable();
    expect(screen.queryByText(/pts away · touch at/)).not.toBeInTheDocument();

    getEngineState.mockResolvedValue(
      state({
        levels: [
          {
            label: 'R1',
            level_price: 24_660,
            role: 'resistance',
            state: 'approaching',
            break_pending: false,
            alerts_remaining: 2
          }
        ]
      })
    );
    renderPage();
    expect(await screen.findByText(/10 pts away · touch at ±6/)).toBeInTheDocument();
  });
});

describe('the levels table', () => {
  it('shows each level with its state named in words', async () => {
    renderPage();
    const table = await levelsTable();

    expect(await within(table).findByText('Touched')).toBeInTheDocument();
    expect(within(table).getByText('Idle')).toBeInTheDocument();
  });

  it('calls out a level that has flipped role', async () => {
    // R1 acting as support means it broke and has not been reclaimed. This is
    // the single most useful thing the page can say.
    getEngineState.mockResolvedValue(
      state({
        levels: [
          {
            label: 'R1',
            level_price: 24_700,
            role: 'support',
            state: 'broken',
            break_pending: false,
            alerts_remaining: 3
          }
        ]
      })
    );
    renderPage();
    const table = await levelsTable();

    expect(await within(table).findByText('Broken')).toBeInTheDocument();
    const row = within(table).getByText('flipped').closest('tr') as HTMLElement;
    // Scoped to R1's own row: S1 is a support too, and the assertion has to
    // be about the level that changed sides.
    expect(within(row).getByText('support')).toBeInTheDocument();
  });

  it('places the LTP between the levels above it and the levels below', async () => {
    renderPage();
    const table = await levelsTable();

    expect(await within(table).findByText('LTP')).toBeInTheDocument();
    expect(within(table).getByText('between R1 and S1')).toBeInTheDocument();

    // R1 (24,700) must come before the divider and S1 (24,600) after it.
    const rows = within(table).getAllByRole('row');
    const labels = rows.map((row) => row.textContent ?? '');
    const r1 = labels.findIndex((text) => text.startsWith('R1'));
    const ltp = labels.findIndex((text) => text.startsWith('LTP'));
    const s1 = labels.findIndex((text) => text.startsWith('S1'));
    expect(r1).toBeLessThan(ltp);
    expect(ltp).toBeLessThan(s1);
  });

  it('shows each level signed distance from the last price', async () => {
    renderPage();
    const table = await levelsTable();

    // A real minus sign, so the column stays aligned under tabular numerals.
    expect(await within(table).findByText('+50.00')).toBeInTheDocument();
    expect(within(table).getByText('−50.00')).toBeInTheDocument();
  });

  it('measures the gap to the level below when there is no price yet', async () => {
    getEngineState.mockResolvedValue(state({ last_price: null, last_tick_at: null }));
    renderPage();
    const table = await levelsTable();

    expect(await within(table).findByText('Gap below')).toBeInTheDocument();
    expect(within(table).getByText('100 pts')).toBeInTheDocument();
  });

  it('reports a watched level that has no slot to edit it in', async () => {
    // The API takes twelve marks with any labels where this form offers six.
    // Dropping the row would report a level as Skipped while it is watched.
    getEngineState.mockResolvedValue(
      state({
        levels: [
          {
            label: 'PDH',
            level_price: 24_720,
            role: 'resistance',
            state: 'approaching',
            break_pending: false,
            alerts_remaining: 1
          }
        ]
      })
    );
    renderPage();
    const table = await screen.findByRole('table');

    expect(await within(table).findByText('PDH')).toBeInTheDocument();
    expect(within(table).getByText('Approaching')).toBeInTheDocument();
    expect(within(table).queryByLabelText('PDH price')).not.toBeInTheDocument();
  });

  it('pauses every row rather than claiming a state, when the levels are stale', async () => {
    getEngineState.mockResolvedValue(state({ levels_stale: true, marked_on: '2026-10-30' }));
    renderPage();
    const table = await levelsTable();

    expect(await within(table).findAllByText('Paused')).toHaveLength(2);
    expect(within(table).queryByText('Touched')).not.toBeInTheDocument();
  });

  it('invites marks when the instrument has none', async () => {
    getEngineState.mockResolvedValue(state({ levels: [] }));
    getLevels.mockResolvedValue({ symbol: 'NIFTY', levels: [] });
    renderPage();

    expect(await screen.findByText('No levels for NIFTY')).toBeInTheDocument();
    // The inputs stay: the empty state sits above the table, not instead of it.
    expect(screen.getByLabelText('R3 price')).toBeInTheDocument();
  });
});

describe('editing the levels', () => {
  it('offers nothing to save until something changes', async () => {
    renderPage();
    await levelsTable();

    expect(screen.getByRole('button', { name: /save levels/i })).toBeDisabled();
    expect(screen.getByRole('button', { name: /discard/i })).toBeDisabled();
    expect(screen.getByText('All changes saved')).toBeInTheDocument();
  });

  it('enables save and discard once a price is edited, and warns what saving costs', async () => {
    const user = userEvent.setup();
    renderPage();
    await levelsTable();

    await user.clear(screen.getByLabelText('R2 price'));
    await user.type(screen.getByLabelText('R2 price'), '24800');

    expect(screen.getByRole('button', { name: /save levels/i })).toBeEnabled();
    expect(screen.getByRole('button', { name: /discard/i })).toBeEnabled();
    expect(screen.getByText(/saving resets live state/i)).toBeInTheDocument();
  });

  it('restores the server values on discard', async () => {
    const user = userEvent.setup();
    renderPage();
    await levelsTable();

    await user.clear(screen.getByLabelText('R1 price'));
    await user.type(screen.getByLabelText('R1 price'), '24999');
    expect(screen.getByLabelText('R1 price')).toHaveValue(24_999);

    await user.click(screen.getByRole('button', { name: /discard/i }));

    expect(screen.getByLabelText('R1 price')).toHaveValue(24_700);
    expect(setLevels).not.toHaveBeenCalled();
  });

  it('sends only the rows that carry a price', async () => {
    const user = userEvent.setup();
    setLevels.mockResolvedValue({
      symbol: 'NIFTY',
      levels: [{ label: 'R1', price: 24_700, role: 'resistance' }]
    });
    renderPage();
    await levelsTable();

    await user.clear(screen.getByLabelText('S1 price'));
    await user.click(screen.getByRole('button', { name: /save levels/i }));

    await waitFor(() => expect(setLevels).toHaveBeenCalledTimes(1));
    const [, payload] = setLevels.mock.calls[0] as [string, { label: string }[]];
    expect(payload.map((row) => row.label)).toEqual(['R1']);
  });

  it('refuses a support placed above a resistance, before any request', async () => {
    const user = userEvent.setup();
    renderPage();
    await levelsTable();

    await user.clear(screen.getByLabelText('S1 price'));
    await user.type(screen.getByLabelText('S1 price'), '24800');

    expect(await screen.findByText(/above a resistance/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save levels/i })).toBeDisabled();
    expect(setLevels).not.toHaveBeenCalled();
  });
});

describe('stale levels', () => {
  const stale = () => state({ levels_stale: true, marked_on: '2026-10-30' });

  it('says which session they are from and that nothing will fire', async () => {
    getEngineState.mockResolvedValue(stale());
    renderPage();

    const banner = await screen.findByRole('status', { name: /stale levels/i });
    expect(within(banner).getByText(/These NIFTY levels are from Fri 30 Oct/)).toBeInTheDocument();
    expect(within(banner).getByText(/No alerts fire for NIFTY/)).toBeInTheDocument();
  });

  it('offers both ways out', async () => {
    getEngineState.mockResolvedValue(stale());
    renderPage();

    const banner = await screen.findByRole('status', { name: /stale levels/i });
    expect(within(banner).getByRole('button', { name: /carry forward/i })).toBeEnabled();
    expect(within(banner).getByRole('button', { name: /re-mark levels/i })).toBeEnabled();
  });

  it('carries the same levels forward, unchanged', async () => {
    const user = userEvent.setup();
    getEngineState.mockResolvedValue(stale());
    setLevels.mockResolvedValue({ symbol: 'NIFTY', levels: [] });
    renderPage();
    await screen.findByRole('status', { name: /stale levels/i });

    await user.click(screen.getByRole('button', { name: /carry forward/i }));

    await waitFor(() => expect(setLevels).toHaveBeenCalledTimes(1));
    const [symbol, payload] = setLevels.mock.calls[0] as [string, unknown];
    expect(symbol).toBe('NIFTY');
    // Exactly what the server already had — saving is what re-stamps today.
    expect(payload).toEqual([
      { label: 'R1', price: 24_700, role: 'resistance' },
      { label: 'S1', price: 24_600, role: 'support' }
    ]);
  });

  it('clears the banner once the refetched levels are current', async () => {
    const user = userEvent.setup();
    getEngineState.mockResolvedValue(stale());
    setLevels.mockResolvedValue({ symbol: 'NIFTY', levels: [] });
    renderPage();
    await screen.findByRole('status', { name: /stale levels/i });

    getEngineState.mockResolvedValue(state({ marked_on: '2026-11-02' }));
    await user.click(screen.getByRole('button', { name: /carry forward/i }));

    await waitFor(() =>
      expect(screen.queryByRole('status', { name: /stale levels/i })).not.toBeInTheDocument()
    );
    expect(await screen.findByText(/Levels carried forward for NIFTY/)).toBeInTheDocument();
  });

  it('clears the inputs and takes the cursor to the first slot on re-mark', async () => {
    const user = userEvent.setup();
    getEngineState.mockResolvedValue(stale());
    renderPage();
    await levelsTable();

    await user.click(screen.getByRole('button', { name: /re-mark levels/i }));

    expect(screen.getByLabelText('R1 price')).toHaveValue(null);
    expect(screen.getByLabelText('S1 price')).toHaveValue(null);
    expect(screen.getByLabelText('R3 price')).toHaveFocus();
  });

  it('cannot carry forward an instrument with no marks at all', async () => {
    getEngineState.mockResolvedValue(stale());
    getLevels.mockResolvedValue({ symbol: 'NIFTY', levels: [] });
    renderPage();

    const banner = await screen.findByRole('status', { name: /stale levels/i });
    await waitFor(() =>
      expect(within(banner).getByRole('button', { name: /carry forward/i })).toBeDisabled()
    );
  });

  it('ranks the stale warning above the unscaled-bands one', async () => {
    // Both can be true at once. Unscaled bands make alerts the wrong size;
    // stale levels stop them entirely, so that is the one to read first.
    getEngineState.mockResolvedValue(state({ levels_stale: true, bands: UNSCALED }));
    renderPage();

    await screen.findByRole('status', { name: /stale levels/i });
    expect(screen.queryByText(/ATR unavailable —/)).not.toBeInTheDocument();
  });

  it('flags the affected index on the tab bar', async () => {
    getWatchlist.mockResolvedValue(watchlist([{ levels_stale: true }, {}, {}]));
    renderPage();

    const tabs = await screen.findByRole('tablist', { name: /watched instruments/i });
    expect(within(tabs).getByText('6 levels · stale')).toBeInTheDocument();
  });
});

describe("today's alerts", () => {
  it('says it is quiet rather than showing an empty list', async () => {
    renderPage();
    expect(await screen.findByText('Quiet so far')).toBeInTheDocument();
  });

  it('lists what went out, newest first', async () => {
    getAlerts.mockResolvedValue({
      symbol: 'NIFTY',
      session: '2026-11-02',
      alerts: [
        alert({ label: 'S1', kind: 'break_confirmed', at: tickAt(60) }),
        alert({ label: 'R1', kind: 'touched', at: tickAt(600) })
      ]
    });
    renderPage();

    const list = await screen.findByRole('list');
    const items = within(list).getAllByRole('listitem');
    expect(items[0]).toHaveTextContent('S1');
    expect(items[1]).toHaveTextContent('R1');
    expect(screen.getByText('2 sent')).toBeInTheDocument();
  });

  it('names the role flip on a break, which is the actionable half', async () => {
    getAlerts.mockResolvedValue({
      symbol: 'NIFTY',
      session: '2026-11-02',
      alerts: [
        alert({
          kind: 'break_confirmed',
          role_before: 'resistance',
          role_after: 'support',
          channels: ['telegram', 'whatsapp']
        })
      ]
    });
    renderPage();

    expect(await screen.findByText(/now acting as support/)).toBeInTheDocument();
    expect(screen.getByText('Telegram · WhatsApp')).toBeInTheDocument();
  });

  it('calls out an alert that reached nobody', async () => {
    // The engine fired and no channel took it: a fault, and invisible if this
    // rendered as a blank line.
    getAlerts.mockResolvedValue({
      symbol: 'NIFTY',
      session: '2026-11-02',
      alerts: [alert({ channels: [] })]
    });
    renderPage();

    expect(await screen.findByText('Not delivered')).toBeInTheDocument();
  });

  it('falls back to the empty state against a backend without the endpoint', async () => {
    getAlerts.mockRejectedValue(new Error('404 Not Found'));
    renderPage();

    expect(await screen.findByText('Quiet so far')).toBeInTheDocument();
    expect(await screen.findByRole('heading', { name: 'Trade Buddy' })).toBeInTheDocument();
  });

  it('loads the log for the selected index', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('tablist', { name: /watched instruments/i });
    await waitFor(() => expect(getAlerts).toHaveBeenCalledWith('NIFTY'));

    await user.click(screen.getByRole('tab', { name: /BANKNIFTY/ }));

    await waitFor(() => expect(getAlerts).toHaveBeenCalledWith('BANKNIFTY'));
  });
});

describe('the instrument tabs', () => {
  it('shows all three indices, watched or not', async () => {
    renderPage();
    const tabs = await screen.findByRole('tablist', { name: /watched instruments/i });

    for (const symbol of ['NIFTY', 'BANKNIFTY', 'SENSEX']) {
      expect(within(tabs).getByText(symbol)).toBeInTheDocument();
    }
  });

  it('says an index is armed when it is marked and quiet', async () => {
    renderPage();
    const tabs = await screen.findByRole('tablist', { name: /watched instruments/i });

    expect(within(tabs).getAllByText('6 levels · armed')).toHaveLength(2);
  });

  it('marks an unmarked index as having no levels rather than omitting it', async () => {
    // An index you forgot to mark produces no alerts all day, and absence is
    // the one state that looks identical to "nothing happened".
    renderPage();
    const tabs = await screen.findByRole('tablist', { name: /watched instruments/i });

    expect(within(tabs).getByText('No levels')).toBeInTheDocument();
  });

  it('names the urgent state in words on the affected index', async () => {
    getWatchlist.mockResolvedValue(
      watchlist([{}, { attention: 'broken', nearest_label: 'S2', nearest_distance: 18 }, {}])
    );
    renderPage();
    const tabs = await screen.findByRole('tablist', { name: /watched instruments/i });

    expect(within(tabs).getByText(/Broken · S2 18 pts/)).toBeInTheDocument();
  });

  it('flags an index whose bands fell back to unscaled points', async () => {
    getWatchlist.mockResolvedValue(watchlist([{}, { band_source: 'points' }, {}]));
    renderPage();
    const tabs = await screen.findByRole('tablist', { name: /watched instruments/i });

    expect(within(tabs).getByText(/unscaled/)).toBeInTheDocument();
  });

  it('marks the selected index as the active tab', async () => {
    renderPage();
    const tabs = await screen.findByRole('tablist', { name: /watched instruments/i });

    expect(within(tabs).getByRole('tab', { name: /^NIFTY/ })).toHaveAttribute(
      'aria-selected',
      'true'
    );
  });

  it('refetches everything for the newly selected index', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('tablist', { name: /watched instruments/i });
    await waitFor(() => expect(getEngineState).toHaveBeenCalledWith('NIFTY'));

    await user.click(screen.getByRole('tab', { name: /BANKNIFTY/ }));

    await waitFor(() => expect(getEngineState).toHaveBeenCalledWith('BANKNIFTY'));
    expect(getLevels).toHaveBeenCalledWith('BANKNIFTY');
    expect(getSettings).toHaveBeenCalledWith('BANKNIFTY');
  });

  it('falls back to an index when the terminal-wide selection is a stock', async () => {
    // The shared picker offers two hundred names; this page watches three.
    renderPage('/tools/trade-buddy?symbol=RELIANCE');

    await waitFor(() => expect(getEngineState).toHaveBeenCalledWith('NIFTY'));
    expect(getEngineState).not.toHaveBeenCalledWith('RELIANCE');
  });
});

describe('the delivery chips', () => {
  it('says Telegram is ready, in words', async () => {
    renderPage();
    expect(await screen.findByRole('button', { name: /telegram ready/i })).toBeInTheDocument();
  });

  it('says it is not set up before anything is connected', async () => {
    getChannels.mockResolvedValue(channels({ configured: false, ready: false, label: null }));
    renderPage();

    expect(await screen.findByRole('button', { name: /telegram not set up/i })).toBeInTheDocument();
  });

  it('shows the WhatsApp budget beside it', async () => {
    renderPage();
    expect(await screen.findByText('2/20')).toBeInTheDocument();
  });
});

describe('band transparency', () => {
  it('warns loudly when the bands are unscaled NIFTY defaults', async () => {
    getEngineState.mockResolvedValue(state({ bands: UNSCALED }));
    renderPage();

    expect(await screen.findByText(/ATR unavailable/i)).toBeInTheDocument();
  });

  it('states where the bands came from in the sensitivity card', async () => {
    renderPage();
    expect(await screen.findByText('ATR(14) scaled')).toBeInTheDocument();
  });

  it('says the bands are point defaults when ATR is offline', async () => {
    getSettings.mockResolvedValue(settings({ bands: UNSCALED }));
    renderPage();

    expect(await screen.findByText(/ATR offline · point defaults/)).toBeInTheDocument();
  });
});

describe('the sensitivity card', () => {
  it('offers all six thresholds', async () => {
    renderPage();
    await screen.findByRole('heading', { name: 'Sensitivity' });

    for (const label of [
      /touch band/i,
      /approach band/i,
      /break buffer/i,
      /confirm hold/i,
      /cooldown/i,
      /daily cap/i
    ]) {
      expect(screen.getByLabelText(label)).toBeInTheDocument();
    }
  });

  it('shows the multiple and the resolved points together', async () => {
    // A multiple alone is abstract; points alone cannot be compared across
    // indices. The setting is only tunable as both.
    renderPage();
    expect(await screen.findByText('0.030 x ATR = 6.0 pts')).toBeInTheDocument();
    expect(screen.getByText('0.060 x ATR = 12.0 pts')).toBeInTheDocument();
  });

  it('places the value in force as the placeholder, so blank still informs', async () => {
    renderPage();
    const touch = await screen.findByLabelText(/touch band/i);
    expect(touch).toHaveValue(null);
    expect(touch).toHaveAttribute('placeholder', '6');
  });

  it('starts on Default when nothing is overridden', async () => {
    renderPage();
    const group = await screen.findByRole('radiogroup', { name: /alert sensitivity/i });

    expect(within(group).getByRole('radio', { name: 'Default' })).toBeChecked();
    expect(within(group).getByRole('radio', { name: 'Custom' })).toBeDisabled();
  });

  it('writes all three bands from one preset', async () => {
    const user = userEvent.setup();
    setSettings.mockResolvedValue(settings());
    renderPage();
    await screen.findByRole('heading', { name: 'Sensitivity' });

    await user.click(screen.getByRole('radio', { name: 'Tight' }));
    await user.click(screen.getByRole('button', { name: /save settings/i }));

    await waitFor(() => expect(setSettings).toHaveBeenCalledTimes(1));
    const [, overrides] = setSettings.mock.calls[0] as [string, Record<string, unknown>];
    // 0.7x the ATR-scaled defaults, so the button means the same thing on
    // every index.
    expect(overrides.touch).toBe(4.2);
    expect(overrides.approach).toBe(17.5);
    expect(overrides.break_buffer).toBe(8.4);
    // The throttles are a separate thought and no preset touches them.
    expect(overrides.cooldown_minutes).toBeNull();
    expect(overrides.daily_alert_cap).toBeNull();
  });

  it('reports Custom once a field is edited away from a preset', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { name: 'Sensitivity' });

    await user.click(screen.getByRole('radio', { name: 'Wide' }));
    expect(screen.getByRole('radio', { name: 'Wide' })).toBeChecked();

    await user.clear(screen.getByLabelText(/touch band/i));
    await user.type(screen.getByLabelText(/touch band/i), '7');

    expect(screen.getByRole('radio', { name: 'Custom' })).toBeChecked();
  });

  it('saves only the fields that were filled in', async () => {
    const user = userEvent.setup();
    setSettings.mockResolvedValue(settings());
    renderPage();
    await screen.findByRole('heading', { name: 'Sensitivity' });

    await user.type(screen.getByLabelText(/break buffer/i), '40');
    await user.click(screen.getByRole('button', { name: /save settings/i }));

    await waitFor(() => expect(setSettings).toHaveBeenCalledTimes(1));
    const [symbol, overrides] = setSettings.mock.calls[0] as [string, Record<string, unknown>];
    expect(symbol).toBe('NIFTY');
    expect(overrides.break_buffer).toBe(40);
    // Everything untouched stays null, meaning "use the scaled default".
    expect(overrides.touch).toBeNull();
    expect(overrides.cooldown_minutes).toBeNull();
  });

  it('refuses a touch band wider than the approach band, before any request', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('heading', { name: 'Sensitivity' });

    await user.type(screen.getByLabelText(/touch band/i), '50');
    await user.type(screen.getByLabelText(/approach band/i), '25');

    expect(await screen.findByText(/TOUCHED before APPROACHING/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save settings/i })).toBeDisabled();
    expect(setSettings).not.toHaveBeenCalled();
  });

  it('reports how many fields are overridden', async () => {
    getSettings.mockResolvedValue(
      settings({
        overrides: {
          touch: 10,
          approach: null,
          break_buffer: 30,
          confirm_hold_seconds: null,
          cooldown_minutes: null,
          daily_alert_cap: null
        }
      })
    );
    renderPage();

    expect(await screen.findByText(/2 overrides/)).toBeInTheDocument();
  });

  it('clears every override on reset', async () => {
    const user = userEvent.setup();
    setSettings.mockResolvedValue(settings());
    getSettings.mockResolvedValue(
      settings({
        overrides: {
          touch: 10,
          approach: null,
          break_buffer: null,
          confirm_hold_seconds: null,
          cooldown_minutes: null,
          daily_alert_cap: null
        }
      })
    );
    renderPage();
    await waitFor(() => expect(screen.getByLabelText(/touch band/i)).toHaveValue(10));

    await user.click(screen.getByRole('button', { name: /reset to defaults/i }));

    expect(screen.getByLabelText(/touch band/i)).toHaveValue(null);
    expect(screen.getByText(/all defaults/)).toBeInTheDocument();
  });
});

describe('the delivery card', () => {
  it('states which step the connection is on, in words', async () => {
    renderPage();
    const card = await screen.findByRole('region', { name: /delivery/i });

    expect(await within(card).findByText('Ready')).toBeInTheDocument();
    expect(within(card).getByText(/@my_alerts_bot/)).toBeInTheDocument();
  });

  it('hides the token field once a token is stored', async () => {
    // Replacing a working token is the rarest thing here, and an empty
    // password field at the top made a finished setup look unfinished.
    renderPage();
    await screen.findByRole('region', { name: /delivery/i });
    await screen.findByRole('button', { name: /replace token/i });

    expect(screen.queryByLabelText(/replace bot token/i)).not.toBeInTheDocument();
  });

  it('brings the token field back on request', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('region', { name: /delivery/i });
    await user.click(await screen.findByRole('button', { name: /replace token/i }));

    expect(screen.getByLabelText(/replace bot token/i)).toBeInTheDocument();
  });

  it('explains that a bot cannot open the conversation, when no chat is linked', async () => {
    getChannels.mockResolvedValue(channels({ target: null, ready: false, verified: false }));
    renderPage();

    expect(await screen.findByText('Needs a chat')).toBeInTheDocument();
    expect(screen.getByText(/a bot cannot open a conversation/i)).toBeInTheDocument();
  });

  it('points at BotFather before anything is connected', async () => {
    getChannels.mockResolvedValue(channels({ configured: false, ready: false, label: null }));
    renderPage();

    expect(await screen.findByText('Not connected')).toBeInTheDocument();
    expect(screen.getByText('@BotFather')).toBeInTheDocument();
    expect(screen.getByLabelText(/bot token/i)).toBeInTheDocument();
  });

  it('says alerts are computed but not delivered while paused', async () => {
    // The distinction that matters: paused is not broken, and the copy has to
    // make that unambiguous or a quiet phone reads as a bug.
    getChannels.mockResolvedValue(channels({ enabled: false, ready: false }));
    renderPage();

    expect(await screen.findByText('Paused')).toBeInTheDocument();
    expect(screen.getByText(/Connected, but switched off/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /resume alerts/i })).toBeInTheDocument();
  });

  it('offers the channel test only once it can actually deliver', async () => {
    getChannels.mockResolvedValue(channels({ target: null, ready: false }));
    renderPage();

    await screen.findByText('Needs a chat');
    expect(screen.queryByRole('button', { name: /send test message/i })).not.toBeInTheDocument();
  });

  it('holds the level-alert test, disabled until there are levels to alert on', async () => {
    getEngineState.mockResolvedValue(state({ levels: [] }));
    getLevels.mockResolvedValue({ symbol: 'NIFTY', levels: [] });
    renderPage();

    await screen.findByText('No levels for NIFTY');
    expect(screen.getByRole('button', { name: /send test alert/i })).toBeDisabled();
  });

  it('reports back what the level-alert test actually sent', async () => {
    const user = userEvent.setup();
    fireTestAlert.mockResolvedValue({
      delivered: true,
      kind: 'touched',
      rendered: 'NIFTY R1 touched. Level 24,700.00, price 24,700.00'
    });
    renderPage();
    await levelsTable();

    await user.click(screen.getByRole('button', { name: /send test alert/i }));

    expect(await screen.findByText(/R1 touched/)).toBeInTheDocument();
  });

  it('shows the WhatsApp budget with the window it applies to', async () => {
    renderPage();
    const card = await screen.findByRole('region', { name: /delivery/i });

    expect(await within(card).findByText('2 / 20')).toBeInTheDocument();
    expect(within(card).getByText(/Rolling four-hour window/)).toBeInTheDocument();
  });

  it('says the bot is separate from the Settings one', async () => {
    // The whole reason for a second bot; if the page does not say it, the
    // natural assumption is that this duplicates Settings → Channels.
    renderPage();
    expect(await screen.findByText(/Separate from Settings/)).toBeInTheDocument();
  });
});

describe('surviving a backend version skew', () => {
  it('renders when /state answers without the bands field', async () => {
    // Regression: a backend predating `bands` answers 200 with a payload that
    // simply lacks it. The page reached through it and crashed the render,
    // which surfaced as a 500 page rather than a missing line. A frontend
    // deployed ahead of its backend must degrade, not white-screen.
    const { bands: _dropped, ...withoutBands } = state();
    getEngineState.mockResolvedValue(withoutBands);

    renderPage();

    expect(await screen.findByRole('heading', { name: 'Trade Buddy' })).toBeInTheDocument();
    expect(await screen.findByRole('table')).toBeInTheDocument();
    // The callout needs a band to compare against, so it is simply absent.
    expect(screen.queryByText(/pts away · touch at/)).not.toBeInTheDocument();
  });

  it('renders when the watchlist endpoint is missing entirely', async () => {
    getWatchlist.mockRejectedValue(new Error('404 Not Found'));

    renderPage();

    expect(await screen.findByRole('heading', { name: 'Trade Buddy' })).toBeInTheDocument();
    expect(screen.queryByRole('tablist')).not.toBeInTheDocument();
  });

  it('renders when the settings endpoint is missing entirely', async () => {
    getSettings.mockRejectedValue(new Error('404 Not Found'));

    renderPage();

    expect(await screen.findByRole('heading', { name: 'Trade Buddy' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'Sensitivity' })).not.toBeInTheDocument();
  });

  it('renders when the channels endpoint is missing entirely', async () => {
    getChannels.mockRejectedValue(new Error('404 Not Found'));
    renderPage();

    expect(await screen.findByRole('heading', { name: 'Trade Buddy' })).toBeInTheDocument();
    expect(await screen.findByText('Not connected')).toBeInTheDocument();
  });
});
