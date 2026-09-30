/**
 * A stand-in for the backend, started by playwright.config.ts.
 *
 * The e2e suite exists to test *this* app's routing, guards and rendering, not
 * the API. Pointing `API_INTERNAL_URL` at this process makes those tests
 * hermetic: no database, no seeded account, and a signed-out visitor is
 * reproducible rather than dependent on whatever cookies happen to be around.
 *
 * Authentication is deliberately crude — a request is signed in when it carries
 * `mc_session=test`. Tests opt in by setting that cookie.
 *
 * Market data is fully deterministic (fixed prices, fixed clock, seeded strike
 * ladder). The parity suite pixel-compares two apps against this, so anything
 * that moved between the two page loads would read as a migration defect.
 */
import { createServer } from 'node:http';

const PORT = Number(process.env.STUB_API_PORT ?? 8099);

const USER = {
  id: '00000000-0000-4000-8000-000000000001',
  email: 'test@marketcompass.local',
  phone: '+919876543210',
  display_name: 'Test User',
  status: 'active',
  email_verified: true,
  created_at: '2026-01-01T00:00:00Z'
};

const PROVENANCE = { source: 'mock', age_seconds: 0, fetched_at: '2026-01-01T10:00:00Z' };

const SPOTS = {
  NIFTY: { price: '24500.25', change: '112.40', change_percent: '0.46' },
  SENSEX: { price: '80250.75', change: '-180.20', change_percent: '-0.22' },
  BANKNIFTY: { price: '52100.50', change: '340.10', change_percent: '0.66' }
};

/**
 * The session's latched opening gap, as the real `/market/spot` now returns it.
 *
 * Fixed values, like everything else here: the point of this stub is a page
 * that renders the same way on every run. `day_open` and `previous_close` are
 * served alongside because the wire carries both, but the card reads `gap`.
 */
const GAPS = {
  NIFTY: { opened_at: '24438.00', reference_close: '24387.85', points: '50.15', percent: '0.21' },
  SENSEX: {
    opened_at: '80120.00',
    reference_close: '80431.00',
    points: '-311.00',
    percent: '-0.39'
  },
  BANKNIFTY: {
    opened_at: '51960.00',
    reference_close: '51760.40',
    points: '199.60',
    percent: '0.39'
  }
};

function sessionGap(instrument) {
  const gap = GAPS[instrument] ?? GAPS.NIFTY;
  const points = Number.parseFloat(gap.points);
  return {
    ...gap,
    signal:
      Math.abs(Number.parseFloat(gap.percent)) < 0.15 ? 'flat' : points > 0 ? 'gap_up' : 'gap_down',
    source: 'mock',
    observed_at: '2026-01-01T03:45:30Z',
    settled: true
  };
}

const FUTURES = {
  NIFTY: { contract: 'NSE:NIFTY26JANFUT', price: '24540.00', change_percent: '0.48' },
  SENSEX: { contract: 'BSE:SENSEX26JANFUT', price: '80310.00', change_percent: '-0.20' },
  BANKNIFTY: { contract: 'NSE:BANKNIFTY26JANFUT', price: '52180.00', change_percent: '0.70' }
};

/** A 21-strike ladder around the spot, with values that vary but never move. */
function optionChain(instrument) {
  const spot = Number.parseFloat(SPOTS[instrument]?.price ?? SPOTS.NIFTY.price);
  const step = instrument === 'SENSEX' ? 100 : 50;
  const atm = Math.round(spot / step) * step;

  const strikes = [];
  let totalCallOi = 0;
  let totalPutOi = 0;

  for (let i = -10; i <= 10; i += 1) {
    const strike = atm + i * step;
    // Deterministic pseudo-variation: no clock, no randomness.
    const wobble = ((i + 10) * 37) % 23;
    const callOi = 120_000 + wobble * 5_000 - i * 3_000;
    const putOi = 118_000 + wobble * 4_200 + i * 3_400;
    totalCallOi += callOi;
    totalPutOi += putOi;

    strikes.push({
      strike: strike.toFixed(2),
      ce: {
        ltp: (Math.max(spot - strike, 0) + 60 + wobble).toFixed(2),
        oi: callOi,
        oi_change: (i % 3) - 1 === 0 ? 0 : ((i % 3) - 1) * 4_500 - wobble * 120,
        volume: 40_000 + wobble * 900,
        iv: (13.5 + wobble * 0.11).toFixed(2),
        bid: null,
        ask: null,
        delta: null
      },
      pe: {
        ltp: (Math.max(strike - spot, 0) + 58 + wobble).toFixed(2),
        oi: putOi,
        oi_change: (i % 4) - 2 === 0 ? 0 : ((i % 4) - 2) * 3_900 + wobble * 95,
        volume: 38_500 + wobble * 850,
        iv: (14.1 + wobble * 0.09).toFixed(2),
        bid: null,
        ask: null,
        delta: null
      }
    });
  }

  return {
    instrument,
    expiry: '2026-01-29',
    expiries: ['2026-01-29', '2026-02-26', '2026-03-26'],
    spot_price: spot.toFixed(2),
    atm_strike: atm.toFixed(2),
    pcr: (totalPutOi / totalCallOi).toFixed(2),
    lot_size: instrument === 'BANKNIFTY' ? 15 : 75,
    change_percent: SPOTS[instrument]?.change_percent ?? '0.00',
    future_price: FUTURES[instrument]?.price ?? null,
    india_vix: '13.85',
    india_vix_change_percent: '-1.20',
    iv_percentile: '42.5',
    total_call_oi: totalCallOi,
    total_put_oi: totalPutOi,
    strikes,
    provenance: PROVENANCE
  };
}

/** 09:15 IST on the fixed stub date, as UTC ms. */
const SESSION_OPEN_MS = Date.parse('2026-01-15T03:45:00Z');
/** The ingest cadence, so the series looks like a real archived session. */
const FRAME_MS = 180_000;
/** 09:15 to 15:30 inclusive. */
const FRAME_COUNT = 126;

/** The Options Lab OI payload, with a full archived session to scrub over. */
function openInterestView(symbol) {
  const chain = optionChain(symbol in SPOTS ? symbol : 'NIFTY');
  const spot = Number.parseFloat(chain.spot_price);
  const atm = Number.parseFloat(chain.atm_strike);

  const strikes = chain.strikes.map((row, i) => {
    const callNow = row.ce.oi;
    const putNow = row.pe.oi;
    // Deterministic open values, so change/change_total modes have real shape.
    const callOpen = callNow - (((i * 13) % 17) - 8) * 2_500;
    const putOpen = putNow - (((i * 7) % 19) - 9) * 2_200;
    return {
      strike: Number.parseFloat(row.strike),
      call_oi_open: callOpen,
      call_oi_now: callNow,
      call_oi_chg: callNow - callOpen,
      call_oi_chg_pct: callOpen ? ((callNow - callOpen) / callOpen) * 100 : 0,
      put_oi_open: putOpen,
      put_oi_now: putNow,
      put_oi_chg: putNow - putOpen,
      put_oi_chg_pct: putOpen ? ((putNow - putOpen) / putOpen) * 100 : 0
    };
  });

  const strikeList = strikes.map((s) => s.strike);
  const step = symbol === 'SENSEX' ? 100 : 50;

  // A full session, so the time slider has something real to scrub over. Every
  // value is a pure function of the frame number — no clock, no randomness —
  // because the parity suite pixel-compares two apps against this payload.
  const series = Array.from({ length: FRAME_COUNT }, (_, frame) => {
    const ratio = frame / (FRAME_COUNT - 1);
    // A single slow arc: down through the morning, back up into the close. That
    // is enough for the ATM band and spot line to visibly travel when scrubbed.
    const frameSpot = spot + step * 3 * (Math.cos(Math.PI * 2 * ratio) - 1) * 0.5;
    return {
      t: new Date(SESSION_OPEN_MS + frame * FRAME_MS).toISOString(),
      strikes: strikeList,
      call: strikes.map((s) => Math.round(s.call_oi_open + s.call_oi_chg * ratio)),
      put: strikes.map((s) => Math.round(s.put_oi_open + s.put_oi_chg * ratio)),
      spot: Math.round(frameSpot * 100) / 100,
      atm: Math.round(frameSpot / step) * step,
      max_pain: Math.round((frameSpot - step * 2) / step) * step
    };
  });
  const frameTimes = series.map((f) => f.t);

  const totalCall = strikes.reduce((a, s) => a + s.call_oi_now, 0);
  const totalPut = strikes.reduce((a, s) => a + s.put_oi_now, 0);

  return {
    instrument_id: '1',
    symbol,
    spot,
    atm_strike: atm,
    max_pain: atm - (symbol === 'SENSEX' ? 200 : 100),
    lot_size: symbol === 'BANKNIFTY' ? 15 : 75,
    expiry_date: '2026-01-29',
    pcr_oi: totalPut / totalCall,
    pcr_change: 0.03,
    open_ts: frameTimes[0],
    now_ts: frameTimes[frameTimes.length - 1],
    data_quality: 'intraday',
    // A full session captured from the bell, so the baseline is a real frame.
    open_is_estimated: false,
    total_call_oi: totalCall,
    total_put_oi: totalPut,
    total_call_oi_chg: strikes.reduce((a, s) => a + s.call_oi_chg, 0),
    total_put_oi_chg: strikes.reduce((a, s) => a + s.put_oi_chg, 0),
    sentiment: {
      label: 'Bullish',
      bullish_pct: 62,
      insight: 'Call writers are defending the upper strikes while puts add near ATM.',
      analysis: 'Net OI build-up favours the upside into expiry, with support holding below ATM.'
    },
    strikes,
    series
  };
}

/** How many model steps one interval covers, mirroring the real service. */
const SERIES_BUCKETS = { '1m': 1, '5m': 5, '15m': 15, '1h': 60 };

/**
 * The Multi OI & Volume payload: a shared time axis plus per-contract arrays.
 *
 * Deterministic like everything else here — the parity suite pixel-compares
 * against it, so a value that moved between two page loads would read as a
 * migration defect rather than as live data.
 */
function oiSeriesView(symbol, interval) {
  const chain = optionChain(symbol in SPOTS ? symbol : 'NIFTY');
  const spot = Number.parseFloat(chain.spot_price);
  const atm = Number.parseFloat(chain.atm_strike);
  const step = symbol === 'SENSEX' ? 100 : 50;
  const stride = SERIES_BUCKETS[interval] ?? 1;

  const points = [];
  for (let frame = 0; frame < FRAME_COUNT; frame += stride) points.push(frame);

  const t = points.map((frame) => new Date(SESSION_OPEN_MS + frame * FRAME_MS).toISOString());
  // `null` at the open, exactly as the reconstructed 09:15 frame arrives.
  const fut = points.map((frame, i) =>
    i === 0 ? null : Math.round((spot + step * 0.6 * Math.sin(frame / 9)) * 100) / 100
  );

  const contracts = [];
  for (let offset = -10; offset <= 10; offset += 1) {
    const strike = atm + offset * step;
    for (const side of ['CE', 'PE']) {
      // A fixed hump around ATM plus a steady build, so `oi[i] - oi[0]` is
      // always positive and the change chart has real shape.
      const base = 400_000 + Math.round(300_000 * Math.exp(-((offset / 5) ** 2)));
      const rate = 1_500 + (((offset + 10) * (side === 'CE' ? 37 : 43)) % 900);
      contracts.push({
        id: `${strike}${side}`,
        strike,
        option_type: side,
        oi: points.map((frame) => base + rate * frame),
        volume: points.map((frame) => Math.round(rate * frame * 0.4))
      });
    }
  }

  const rank = (key) =>
    [...contracts]
      .sort((a, b) => (b[key].at(-1) ?? 0) - (a[key].at(-1) ?? 0) || a.id.localeCompare(b.id))
      .slice(0, 5)
      .map((contract) => contract.id);

  return {
    instrument_id: '1',
    symbol,
    expiry_date: '2026-01-29',
    atm_strike: atm,
    lot_size: symbol === 'BANKNIFTY' ? 15 : 75,
    open_ts: t[0],
    now_ts: t[t.length - 1],
    data_quality: 'intraday',
    open_is_estimated: false,
    interval,
    window: 10,
    t,
    fut,
    contracts,
    default_ids: rank('oi'),
    default_vol_ids: rank('volume')
  };
}

/**
 * The Put-Call Ratio payload: chain-wide totals at the capture cadence.
 *
 * Deliberately carries one `null` PCR point. A ratio with no call interest is
 * undefined, and the whole path — resampling, the chart, the tooltip — has to
 * carry that through rather than quietly rendering 0 and drawing a floor.
 */
function pcrSeriesView(symbol) {
  const chain = optionChain(symbol in SPOTS ? symbol : 'NIFTY');
  const spot = Number.parseFloat(chain.spot_price);
  const step = symbol === 'SENSEX' ? 100 : 50;

  const t = [];
  const fut = [];
  const pcr = [];
  const callOi = [];
  const putOi = [];
  const callChg = [];
  const putChg = [];

  for (let frame = 0; frame < FRAME_COUNT; frame += 1) {
    t.push(new Date(SESSION_OPEN_MS + frame * FRAME_MS).toISOString());
    fut.push(
      frame === 0 ? null : Math.round((spot + step * 0.6 * Math.sin(frame / 9)) * 100) / 100
    );

    const calls = 100_000_000 + frame * 240_000;
    const puts = 92_000_000 + frame * 310_000;
    callOi.push(calls);
    putOi.push(puts);
    callChg.push(frame * 240_000);
    putChg.push(frame * 310_000);
    // One undefined ratio mid-session, standing in for a chain with no calls.
    pcr.push(frame === 40 ? null : Math.round((puts / calls) * 10_000) / 10_000);
  }

  return {
    instrument_id: '1',
    symbol,
    expiry_date: '2026-01-29',
    lot_size: symbol === 'BANKNIFTY' ? 15 : 75,
    open_ts: t[0],
    now_ts: t[t.length - 1],
    data_quality: 'intraday',
    open_is_estimated: false,
    t,
    fut,
    pcr,
    call_oi: callOi,
    put_oi: putOi,
    call_oi_chg: callChg,
    put_oi_chg: putChg
  };
}

/**
 * The Gamma Exposure payload: per-strike dealer gamma at the capture cadence.
 *
 * The profile is shaped, not random. Call gamma is deliberately piled two
 * strikes above ATM and put gamma two below, so the call and put walls land on
 * strikes a test can name; and the net profile runs negative below spot and
 * positive above, so there is exactly one crossing near the money for the flip
 * and the cross to find.
 */
function gexView(symbol) {
  const chain = optionChain(symbol in SPOTS ? symbol : 'NIFTY');
  const spot = Number.parseFloat(chain.spot_price);
  const atm = Number.parseFloat(chain.atm_strike);
  const step = symbol === 'SENSEX' ? 100 : 50;

  const offsets = [];
  for (let offset = -10; offset <= 10; offset += 1) offsets.push(offset);
  const strikes = offsets.map((offset) => atm + offset * step);

  const t = [];
  const frames = [];

  for (let frame = 0; frame < FRAME_COUNT; frame += 1) {
    const at = new Date(SESSION_OPEN_MS + frame * FRAME_MS).toISOString();
    t.push(at);

    // Spot drifts through the session so a scrub visibly moves the markers.
    const frameSpot = Math.round((spot + step * 0.4 * Math.sin(frame / 9)) * 100) / 100;
    const callGex = [];
    const putGex = [];

    for (const offset of offsets) {
      // A gamma hump centred on ATM, plus the two deliberate spikes.
      const hump = Math.exp(-((offset / 4) ** 2));
      const callSpike = offset === 2 ? 3 : 1;
      const putSpike = offset === -2 ? 3 : 1;
      // Calls concentrate above the money and puts below, which is what makes
      // the net profile cross zero once, near spot.
      const callWeight = offset >= 0 ? 1 : 0.25;
      const putWeight = offset <= 0 ? 1 : 0.25;
      callGex.push(Math.round(hump * callSpike * callWeight * 8_000) / 100);
      putGex.push(-Math.round(hump * putSpike * putWeight * 8_000) / 100);
    }

    const net = callGex.map((value, i) => value + putGex[i]);
    const abs = callGex.map((value, i) => Math.abs(value) + Math.abs(putGex[i]));

    frames.push({
      t: at,
      spot: frameSpot,
      atm,
      call_gex: callGex,
      put_gex: putGex,
      net_total: Math.round(net.reduce((a, b) => a + b, 0) * 100) / 100,
      abs_total: Math.round(abs.reduce((a, b) => a + b, 0) * 100) / 100,
      call_wall: atm + 2 * step,
      put_wall: atm - 2 * step,
      gamma_flip: atm - step / 2,
      net_cross: atm + step / 4
    });
  }

  return {
    instrument_id: '1',
    symbol,
    expiry_date: '2026-01-29',
    lot_size: symbol === 'BANKNIFTY' ? 15 : 75,
    spot: frames[frames.length - 1].spot,
    atm_strike: atm,
    open_ts: t[0],
    now_ts: t[t.length - 1],
    data_quality: 'intraday',
    open_is_estimated: false,
    iv_coverage: 1,
    strikes,
    t,
    frames
  };
}

/** How many model minutes one interval covers. */
const CANDLE_MINUTES = { '1m': 1, '5m': 5, '15m': 15, '1h': 60, '1d': 375 };

/**
 * OHLC bars for the Analyse page.
 *
 * A deterministic saw around the instrument's spot — no clock and no
 * randomness, because the parity suite pixel-compares against this payload.
 * Each bar is a real high/low envelope around its open and close, so the
 * candles have bodies and wicks rather than being flat lines.
 */
function historyView(symbol, interval, days) {
  const spot = Number.parseFloat((SPOTS[symbol] ?? SPOTS.NIFTY).price);
  const minutes = CANDLE_MINUTES[interval] ?? 5;
  const perDay = Math.max(1, Math.floor(375 / minutes));

  const candles = [];
  const total = Math.min(400, perDay * days);

  for (let i = 0; i < total; i += 1) {
    const phase = (i / 24) * Math.PI * 2;
    const open = spot + Math.sin(phase) * 60;
    const close = spot + Math.sin(phase + 0.35) * 60;
    const t = SESSION_OPEN_MS + i * minutes * 60_000;

    candles.push({
      time: new Date(t).toISOString(),
      open: Math.round(open * 100) / 100,
      high: Math.round((Math.max(open, close) + 18) * 100) / 100,
      low: Math.round((Math.min(open, close) - 18) * 100) / 100,
      close: Math.round(close * 100) / 100,
      // Indices carry no turnover of their own; the page treats an all-zero
      // series as "no volume" and hides the pane, which is worth exercising.
      volume: 0
    });
  }

  return {
    instrument: symbol,
    interval,
    candles,
    provenance: PROVENANCE
  };
}

function send(res, status, body) {
  const payload = body === null ? '' : JSON.stringify(body);
  res.writeHead(status, {
    'content-type': body === null ? 'text/plain' : 'application/json'
  });
  res.end(payload);
}

function problem(res, status, code, detail) {
  res.writeHead(status, { 'content-type': 'application/problem+json' });
  res.end(JSON.stringify({ type: 'about:blank', title: code, status, code, detail }));
}

const server = createServer((req, res) => {
  const url = new URL(req.url ?? '/', `http://localhost:${PORT}`);
  const signedIn = (req.headers.cookie ?? '').includes('mc_session=test');
  const instrument = url.searchParams.get('instrument') ?? 'NIFTY';

  if (url.pathname === '/__stub/health') {
    return send(res, 200, { ok: true });
  }

  if (url.pathname === '/api/v1/auth/me') {
    return signedIn ? send(res, 200, USER) : problem(res, 401, 'session_expired', 'No session.');
  }

  if (url.pathname === '/api/v1/auth/refresh') {
    return problem(res, 401, 'session_expired', 'No session.');
  }

  if (!signedIn) {
    return problem(res, 401, 'session_expired', 'No session.');
  }

  if (url.pathname === '/api/v1/auth/sessions') {
    return send(res, 200, []);
  }

  if (url.pathname === '/api/v1/market/status') {
    return send(res, 200, {
      is_open: true,
      session_date: '2026-01-15',
      // Fixed: a live clock would differ between the two screenshots.
      time_ist: '10:46:46 IST',
      provider: 'stub',
      connected: false,
      source: 'mock',
      market_open: '09:15',
      market_close: '15:30'
    });
  }

  if (url.pathname === '/api/v1/market/spot') {
    const spot = SPOTS[instrument] ?? SPOTS.NIFTY;
    const gap = sessionGap(instrument);
    return send(res, 200, {
      instrument,
      ...spot,
      day_open: gap.opened_at,
      previous_close: gap.reference_close,
      gap,
      provenance: PROVENANCE
    });
  }

  if (url.pathname === '/api/v1/market/futures') {
    const fut = FUTURES[instrument] ?? FUTURES.NIFTY;
    return send(res, 200, {
      instrument,
      contract: fut.contract,
      expiry: '2026-01-29',
      price: fut.price,
      change: '112.00',
      change_percent: fut.change_percent,
      volume: 9_450_000,
      day_high: (Number.parseFloat(fut.price) + 85).toFixed(2),
      day_low: (Number.parseFloat(fut.price) - 96).toFixed(2),
      provenance: PROVENANCE
    });
  }

  if (url.pathname === '/api/v1/market/option-chain') {
    return send(res, 200, optionChain(instrument));
  }

  if (url.pathname === '/api/v1/market/history') {
    return send(
      res,
      200,
      historyView(
        instrument in SPOTS ? instrument : 'NIFTY',
        url.searchParams.get('interval') ?? '5m',
        Number.parseInt(url.searchParams.get('days') ?? '5', 10)
      )
    );
  }

  if (url.pathname.startsWith('/api/v1/options-lab/gex/')) {
    const symbol = decodeURIComponent(url.pathname.split('/').pop() ?? 'NIFTY');
    return send(res, 200, gexView(symbol));
  }

  if (url.pathname.startsWith('/api/v1/options-lab/pcr-series/')) {
    const symbol = decodeURIComponent(url.pathname.split('/').pop() ?? 'NIFTY');
    return send(res, 200, pcrSeriesView(symbol));
  }

  if (url.pathname.startsWith('/api/v1/options-lab/oi-series/')) {
    const symbol = decodeURIComponent(url.pathname.split('/').pop() ?? 'NIFTY');
    return send(res, 200, oiSeriesView(symbol, url.searchParams.get('interval') ?? '1m'));
  }

  if (url.pathname.startsWith('/api/v1/options-lab/oi/')) {
    const symbol = decodeURIComponent(url.pathname.split('/').pop() ?? 'NIFTY');
    return send(res, 200, openInterestView(symbol));
  }

  if (url.pathname === '/api/v1/broker/fyers/status') {
    return send(res, 200, {
      status: 'pending',
      configured: false,
      connected: false,
      masked_app_id: null,
      broker_user_id: null,
      display_name: null,
      last_validated_at: null,
      last_error: null,
      redirect_uri: 'http://localhost:5173/settings/broker/callback'
    });
  }

  return problem(res, 404, 'not_found', `No stub route for ${url.pathname}`);
});

server.listen(PORT, () => {
  // Playwright surfaces webServer output prefixed with [WebServer]; this line is
  // how you know the stub, not the real backend, answered a test.
  console.warn(`[stub-api] listening on http://localhost:${PORT}`);
});
