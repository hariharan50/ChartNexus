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
 * *shows* what they decide. Two things matter most and both are asserted here:
 * the feed verdict is stated in words (not just a coloured dot), and a level
 * that has flipped role says so — "R1 broken, now acting as support" is the
 * sentence the whole feature exists to produce.
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
    getChannels: (...args: unknown[]) => getChannels(...args)
  };
});

const TradeBuddy = (await import('../../app/routes/terminal/tools/trade-buddy/route')).default;

/** A tick that just arrived, relative to the real clock. */
function tickAt(secondsAgo: number): string {
  return new Date(Date.now() - secondsAgo * 1000).toISOString();
}

function state(over: Record<string, unknown> = {}) {
  return {
    symbol: 'NIFTY',
    bands: {
      touch: 6,
      approach: 25,
      break_buffer: 12,
      confirm_hold_seconds: 20,
      source: 'atr',
      atr: 200,
      note: null
    },
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

/**
 * A Router is required, not incidental: the page reads the terminal-wide
 * instrument selection through `useSelectedInstrument`, which is backed by the
 * URL so a choice survives navigation between tools.
 */
function settings(over: Record<string, unknown> = {}) {
  return {
    symbol: 'NIFTY',
    bands: {
      touch: 6,
      approach: 25,
      break_buffer: 12,
      confirm_hold_seconds: 20,
      source: 'atr',
      atr: 200,
      note: null
    },
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
    symbol: 'NSE:NIFTY50-INDEX',
    levels: [{ label: 'R1', price: 24_700, role: 'resistance' }]
  });
  getEngineState.mockResolvedValue(state());
  getWatchlist.mockResolvedValue(watchlist());
  getSettings.mockResolvedValue(settings());
  getChannels.mockResolvedValue(channels());
});

describe('the page shell', () => {
  it('names itself and offers the six fixed slots', async () => {
    renderPage();

    expect(await screen.findByRole('heading', { name: 'Trade Buddy' })).toBeInTheDocument();
    for (const label of ['R3', 'R2', 'R1', 'S1', 'S2', 'S3']) {
      expect(screen.getByLabelText(`${label} price`)).toBeInTheDocument();
    }
  });

  it('seeds the form from the saved marks', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByLabelText('R1 price')).toHaveValue(24_700));
    expect(screen.getByLabelText('R2 price')).toHaveValue(null);
  });
});

describe('the feed verdict', () => {
  it('states "Live" in words, not only as a colour', async () => {
    renderPage();
    expect(await screen.findByText('Live')).toBeInTheDocument();
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

  it('shows the last price and the WhatsApp budget', async () => {
    renderPage();
    // Scoped to the strip: the price deliberately appears twice on the page,
    // once here and once as the ladder's cursor chip.
    // Awaited, not synchronous: the strip renders immediately with placeholder
    // dashes, so the region exists well before the state query resolves.
    const strip = await screen.findByRole('region', { name: /watcher status/i });
    expect(await within(strip).findByText('24,650.00')).toBeInTheDocument();
    expect(within(strip).getByText(/2 \/ 20/)).toBeInTheDocument();
  });
});

describe('the live table', () => {
  it('shows each level with its state named in words', async () => {
    renderPage();
    const table = await screen.findByRole('table');
    expect(within(table).getByText('Touched')).toBeInTheDocument();
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

    const table = await screen.findByRole('table');
    expect(within(table).getByText('Broken')).toBeInTheDocument();
    expect(within(table).getByText('flipped')).toBeInTheDocument();
    expect(within(table).getByText('support')).toBeInTheDocument();
  });

  it('invites marks when none are set rather than showing an empty table', async () => {
    getEngineState.mockResolvedValue(state({ levels: [] }));
    getLevels.mockResolvedValue({ symbol: 'NSE:NIFTY50-INDEX', levels: [] });
    renderPage();

    expect(await screen.findByText(/No levels marked yet/i)).toBeInTheDocument();
    expect(screen.queryByRole('table')).not.toBeInTheDocument();
  });
});

describe('saving marks', () => {
  it('sends only the rows that carry a price', async () => {
    const user = userEvent.setup();
    setLevels.mockResolvedValue({
      symbol: 'NSE:NIFTY50-INDEX',
      levels: [{ label: 'R1', price: 24_700, role: 'resistance' }]
    });
    renderPage();
    await waitFor(() => expect(screen.getByLabelText('R1 price')).toHaveValue(24_700));

    await user.click(screen.getByRole('button', { name: /save levels/i }));

    await waitFor(() => expect(setLevels).toHaveBeenCalledTimes(1));
    const [, payload] = setLevels.mock.calls[0] as [string, { label: string }[]];
    expect(payload.map((row) => row.label)).toEqual(['R1']);
  });

  it('refuses a support placed above a resistance, before any request', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByLabelText('R1 price')).toHaveValue(24_700));

    await user.clear(screen.getByLabelText('S1 price'));
    await user.type(screen.getByLabelText('S1 price'), '24800');
    await user.click(screen.getByRole('button', { name: /save levels/i }));

    expect(await screen.findByText(/above a resistance/i)).toBeInTheDocument();
    expect(setLevels).not.toHaveBeenCalled();
  });
});

describe('the test alert', () => {
  it('is disabled until levels exist, since there is nothing to alert on', async () => {
    getEngineState.mockResolvedValue(state({ levels: [] }));
    getLevels.mockResolvedValue({ symbol: 'NSE:NIFTY50-INDEX', levels: [] });
    renderPage();

    await screen.findByText(/No levels marked yet/i);
    expect(screen.getByRole('button', { name: /send test alert/i })).toBeDisabled();
  });

  it('reports back what was actually sent', async () => {
    const user = userEvent.setup();
    fireTestAlert.mockResolvedValue({
      delivered: true,
      kind: 'touched',
      rendered: 'NSE:NIFTY50-INDEX R1 touched. Level 24,700.00, price 24,700.00'
    });
    renderPage();
    await screen.findByRole('table');

    await user.click(screen.getByRole('button', { name: /send test alert/i }));

    expect(await screen.findByText(/R1 touched/)).toBeInTheDocument();
  });
});

describe('the watchlist strip', () => {
  it('shows all three indices, watched or not', async () => {
    renderPage();
    const strip = await screen.findByRole('tablist', { name: /watched instruments/i });

    for (const symbol of ['NIFTY', 'BANKNIFTY', 'SENSEX']) {
      expect(within(strip).getByText(symbol)).toBeInTheDocument();
    }
  });

  it('marks an unmarked index as not watched rather than omitting it', async () => {
    // An index you forgot to mark produces no alerts all day, and absence is
    // the one state that looks identical to "nothing happened".
    renderPage();
    const strip = await screen.findByRole('tablist', { name: /watched instruments/i });

    expect(within(strip).getByText('No levels')).toBeInTheDocument();
    expect(within(strip).getByText('Not watched')).toBeInTheDocument();
  });

  it('names the urgent state in words on the affected index', async () => {
    getWatchlist.mockResolvedValue(watchlist([{}, { attention: 'broken' }, {}]));
    renderPage();
    const strip = await screen.findByRole('tablist', { name: /watched instruments/i });

    expect(within(strip).getByText('Broken')).toBeInTheDocument();
  });

  it('flags an index whose bands fell back to unscaled points', async () => {
    getWatchlist.mockResolvedValue(watchlist([{}, { band_source: 'points' }, {}]));
    renderPage();
    const strip = await screen.findByRole('tablist', { name: /watched instruments/i });

    expect(within(strip).getByText(/unscaled/)).toBeInTheDocument();
  });

  it('marks the selected index as the active tab', async () => {
    renderPage();
    const strip = await screen.findByRole('tablist', { name: /watched instruments/i });

    const nifty = within(strip).getByRole('tab', { name: /^NIFTY/ });
    expect(nifty).toHaveAttribute('aria-selected', 'true');
  });
});

describe('switching instrument', () => {
  it('refetches levels and state for the newly selected index', async () => {
    const user = userEvent.setup();
    renderPage();
    await screen.findByRole('tablist', { name: /watched instruments/i });
    await waitFor(() => expect(getEngineState).toHaveBeenCalledWith('NIFTY'));

    await user.click(screen.getByRole('tab', { name: /BANKNIFTY/ }));

    await waitFor(() => expect(getEngineState).toHaveBeenCalledWith('BANKNIFTY'));
    expect(getLevels).toHaveBeenCalledWith('BANKNIFTY');
  });

  it('names the selected index on both panels', async () => {
    renderPage();
    const marks = await screen.findByRole('heading', { name: /Today's levels/i });
    expect(marks).toHaveTextContent('NIFTY');
  });

  it('falls back to an index when the terminal-wide selection is a stock', async () => {
    // The shared picker offers two hundred names; this page watches three.
    renderPage('/tools/trade-buddy?symbol=RELIANCE');

    await waitFor(() => expect(getEngineState).toHaveBeenCalledWith('NIFTY'));
    expect(getEngineState).not.toHaveBeenCalledWith('RELIANCE');
  });
});

describe('band transparency', () => {
  it('shows the resolved bands and the ATR they came from', async () => {
    renderPage();
    expect(await screen.findByText(/scaled from ATR 200/)).toBeInTheDocument();
    expect(screen.getByText(/buffer 12 pts/)).toBeInTheDocument();
  });

  it('warns loudly when the bands are unscaled NIFTY defaults', async () => {
    getEngineState.mockResolvedValue(
      state({
        bands: {
          touch: 6,
          approach: 25,
          break_buffer: 12,
          confirm_hold_seconds: 20,
          source: 'points',
          atr: null,
          note: null
        }
      })
    );
    renderPage();

    expect(await screen.findByText(/ATR unavailable/i)).toBeInTheDocument();
  });
});

describe('the alert settings panel', () => {
  it('offers all six thresholds', async () => {
    renderPage();
    await screen.findByRole('heading', { name: /Alert settings/i });

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

  it('says the thresholds are unscaled when ATR is missing', async () => {
    getSettings.mockResolvedValue(
      settings({
        bands: {
          touch: 6,
          approach: 25,
          break_buffer: 12,
          confirm_hold_seconds: 20,
          source: 'points',
          atr: null,
          note: null
        }
      })
    );
    renderPage();

    expect(await screen.findByText(/unscaled point defaults sized for NIFTY/i)).toBeInTheDocument();
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

    expect(await screen.findByText('2 overrides')).toBeInTheDocument();
  });

  it('saves only the fields that were filled in', async () => {
    const user = userEvent.setup();
    setSettings.mockResolvedValue(settings());
    renderPage();
    await screen.findByRole('heading', { name: /Alert settings/i });

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
    await screen.findByRole('heading', { name: /Alert settings/i });

    await user.type(screen.getByLabelText(/touch band/i), '50');
    await user.type(screen.getByLabelText(/approach band/i), '25');

    expect(await screen.findByText(/TOUCHED before APPROACHING/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /save settings/i })).toBeDisabled();
    expect(setSettings).not.toHaveBeenCalled();
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
    expect(screen.getByText('All defaults')).toBeInTheDocument();
  });

  it('loads settings for the selected index', async () => {
    const user = userEvent.setup();
    renderPage();
    // The strip has to exist before it can be clicked; the settings call
    // resolves first, so waiting on that alone races the render.
    await screen.findByRole('tablist', { name: /watched instruments/i });
    await waitFor(() => expect(getSettings).toHaveBeenCalledWith('NIFTY'));

    await user.click(screen.getByRole('tab', { name: /BANKNIFTY/ }));

    await waitFor(() => expect(getSettings).toHaveBeenCalledWith('BANKNIFTY'));
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
    // The band line is simply absent.
    expect(screen.queryByText(/scaled from ATR/)).not.toBeInTheDocument();
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
    expect(screen.queryByRole('heading', { name: /Alert settings/i })).not.toBeInTheDocument();
  });
});

describe('the alert channel panel', () => {
  it('states which step the connection is on, in words', async () => {
    renderPage();
    expect(await screen.findByText(/Telegram · Ready/)).toBeInTheDocument();
    expect(screen.getByText('@my_alerts_bot')).toBeInTheDocument();
  });

  it('explains that a bot cannot open the conversation, when no chat is linked', async () => {
    getChannels.mockResolvedValue(channels({ target: null, ready: false, verified: false }));
    renderPage();

    expect(await screen.findByText(/Telegram · Needs a chat/)).toBeInTheDocument();
    expect(screen.getByText(/a bot cannot open a conversation/i)).toBeInTheDocument();
  });

  it('points at BotFather before anything is connected', async () => {
    getChannels.mockResolvedValue(channels({ configured: false, ready: false, label: null }));
    renderPage();

    expect(await screen.findByText(/Telegram · Not connected/)).toBeInTheDocument();
    // Both the <p> and the <strong> inside it match a bare regex; the
    // <strong> is the one that actually carries the name.
    expect(screen.getByText('@BotFather')).toBeInTheDocument();
  });

  it('says alerts are computed but not delivered while paused', async () => {
    // The distinction that matters: paused is not broken, and the copy has to
    // make that unambiguous or a quiet phone reads as a bug.
    getChannels.mockResolvedValue(channels({ enabled: false, ready: false }));
    renderPage();

    expect(await screen.findByText(/Telegram · Paused/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /resume alerts/i })).toBeInTheDocument();
  });

  it('offers the test only once the channel can actually deliver', async () => {
    getChannels.mockResolvedValue(channels({ target: null, ready: false }));
    renderPage();

    await screen.findByText(/Telegram · Needs a chat/);
    expect(screen.queryByRole('button', { name: /send test message/i })).not.toBeInTheDocument();
  });

  it('says the bot is separate from the Settings one', async () => {
    // The whole reason for a second bot; if the page does not say it, the
    // natural assumption is that this duplicates Settings → Channels.
    renderPage();
    expect(await screen.findByText(/separate from the one under Settings/i)).toBeInTheDocument();
  });

  it('renders when the channels endpoint is missing entirely', async () => {
    getChannels.mockRejectedValue(new Error('404 Not Found'));
    renderPage();

    expect(await screen.findByRole('heading', { name: 'Trade Buddy' })).toBeInTheDocument();
    expect(await screen.findByText(/Telegram · Not connected/)).toBeInTheDocument();
  });
});

describe('stale levels', () => {
  it('says loudly that nothing will fire until they are re-marked', async () => {
    getEngineState.mockResolvedValue(state({ levels_stale: true, marked_on: '2026-10-30' }));
    renderPage();

    expect(await screen.findByText(/No alerts will be sent/)).toBeInTheDocument();
    expect(screen.getByText(/2026-10-30/)).toBeInTheDocument();
  });

  it('ranks the stale warning above the unscaled-bands one', async () => {
    // Both can be true at once. Unscaled bands make alerts the wrong size;
    // stale levels stop them entirely, so that is the one to read first.
    getEngineState.mockResolvedValue(
      state({
        levels_stale: true,
        marked_on: '2026-10-30',
        bands: {
          touch: 6,
          approach: 25,
          break_buffer: 12,
          confirm_hold_seconds: 20,
          source: 'points',
          atr: null,
          note: null
        }
      })
    );
    renderPage();

    expect(await screen.findByText(/No alerts will be sent/)).toBeInTheDocument();
    expect(screen.queryByText(/ATR unavailable —/)).not.toBeInTheDocument();
  });

  it('flags the affected index on the watchlist strip', async () => {
    getWatchlist.mockResolvedValue(watchlist([{ levels_stale: true }, {}, {}]));
    renderPage();

    const strip = await screen.findByRole('tablist', { name: /watched instruments/i });
    expect(within(strip).getByText(/stale/)).toBeInTheDocument();
  });

  it('shows nothing when the levels are current', async () => {
    renderPage();
    await screen.findByRole('table');
    expect(screen.queryByText(/No alerts will be sent/)).not.toBeInTheDocument();
  });
});

describe('current levels', () => {
  it('confirms which session they are for', async () => {
    getEngineState.mockResolvedValue(state({ marked_on: '2026-11-02' }));
    renderPage();

    expect(await screen.findByText('Marked for 2026-11-02')).toBeInTheDocument();
  });

  it('drops the confirmation once they go stale', async () => {
    getEngineState.mockResolvedValue(state({ marked_on: '2026-10-30', levels_stale: true }));
    renderPage();

    await screen.findByText(/No alerts will be sent/);
    expect(screen.queryByText(/^Marked for/)).not.toBeInTheDocument();
  });
});
