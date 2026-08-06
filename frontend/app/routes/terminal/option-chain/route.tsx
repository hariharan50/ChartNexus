import { useEffect, useMemo, useRef, useState } from 'react';
import { metrics } from '$contexts/market-data/derive';
import { useOptionChainForExpiryQuery } from '$contexts/market-data/queries';
import { formatInt, formatPrice } from '$shared/formatting/numbers';
import { cx } from '$shared/ui/cx';
import IconChart from '$shared/ui/icons/IconChart';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import IconClock from '$shared/ui/icons/IconClock';
import {
  atmIndex,
  compactIndian,
  daysAwayLabel,
  expiryLabel,
  maxOi,
  num,
  oiChangePct,
  signedPct,
  STRIKE_COUNTS,
  topVolume,
  toStrikes,
  volumeRanks,
  windowAround,
  type Leg,
  type StrikeCount
} from './chain-model';
import BuildupBadge from './components/BuildupBadge';
import OIBar from './components/OIBar';
import VolCell from './components/VolCell';
import s from './route.module.css';

// --- instrument catalog --------------------------------------------------
const CATALOG = [
  { id: 1, short: 'NIFTY', badge: '50', symbol: 'NIFTY' },
  { id: 2, short: 'SENSEX', badge: 'BSE', symbol: 'SENSEX' },
  { id: 3, short: 'BANKNIFTY', badge: 'BNK', symbol: 'BANKNIFTY' }
];

// --- small view helpers --------------------------------------------------
function pctTone(v?: number): 'up' | 'down' | 'flat' {
  if (v == null || Number.isNaN(v)) return 'flat';
  return v > 0 ? 'up' : v < 0 ? 'down' : 'flat';
}
function ltpText(leg?: Leg): string {
  return leg?.ltp != null ? formatPrice(leg.ltp) : '—';
}
function ivText(leg?: Leg, fallback?: Leg): string {
  const iv = leg?.iv ?? fallback?.iv;
  return iv != null ? iv.toFixed(1) : '—';
}

const SKELETON_ROWS = Array.from({ length: 16 }, (_, i) => i);

export default function OptionChain() {
  const [idx, setIdx] = useState(0);
  const [selectedExpiry, setSelectedExpiry] = useState<string | undefined>(undefined);
  const [strikeCount, setStrikeCount] = useState<StrikeCount>(5);

  const instrument = CATALOG[idx] ?? CATALOG[0]!;

  function cycle(delta: number) {
    setIdx((current) => (current + delta + CATALOG.length) % CATALOG.length);
    setSelectedExpiry(undefined); // the previous expiry may not exist on the new instrument
  }

  // --- data ----------------------------------------------------------------
  const chainQ = useOptionChainForExpiryQuery(instrument.symbol, selectedExpiry);

  const chain = chainQ.data;
  const loading = chainQ.isLoading;
  const refreshing = chainQ.isFetching;

  // The whole derivation chain below is O(strikes) and re-runs on every render
  // otherwise — this is the largest table in the app.
  const strikes = useMemo(() => (chain ? toStrikes(chain) : []), [chain]);
  const spot = chain ? num(chain.spot_price) : undefined;
  const spotChange = chain ? num(chain.change_percent) : undefined;
  const future = chain ? num(chain.future_price) : undefined;

  const atmIdx = useMemo(
    () => atmIndex(strikes, spot, chain ? num(chain.atm_strike) : undefined),
    [strikes, spot, chain]
  );
  const atmStrike = atmIdx >= 0 ? strikes[atmIdx]?.strike : undefined;
  const visible = useMemo(
    () => windowAround(strikes, atmIdx, strikeCount),
    [strikes, atmIdx, strikeCount]
  );

  const maxCallOi = useMemo(() => maxOi(visible, 'ce'), [visible]);
  const maxPutOi = useMemo(() => maxOi(visible, 'pe'), [visible]);
  const ceRanks = useMemo(() => volumeRanks(visible, 'ce'), [visible]);
  const peRanks = useMemo(() => volumeRanks(visible, 'pe'), [visible]);
  const maxCEVol = useMemo(() => topVolume(visible, 'ce'), [visible]);
  const maxPEVol = useMemo(() => topVolume(visible, 'pe'), [visible]);

  const m = useMemo(() => (chain ? metrics(chain) : undefined), [chain]);
  const pcr = m?.pcr;
  const maxPain = m?.maxPain;
  const atmIv = useMemo(() => {
    if (atmIdx < 0) return undefined;
    const row = strikes[atmIdx];
    return row?.ce?.iv ?? row?.pe?.iv;
  }, [atmIdx, strikes]);

  const expiries = chain?.expiries?.slice(0, 8) ?? [];
  const currentExpiry = selectedExpiry ?? chain?.expiry ?? '';

  // --- live clock ----------------------------------------------------------
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);
  const clock = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Kolkata',
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false
  }).format(now);

  // Close the expiry menu after a pick.
  const expiryMenu = useRef<HTMLDetailsElement>(null);
  function pickExpiry(exp: string) {
    setSelectedExpiry(exp);
    if (expiryMenu.current) expiryMenu.current.open = false;
  }

  return (
    <div className={s.chainPage}>
      {/* 1. Control bar ------------------------------------------------------ */}
      <section className={cx(s.panel, s.controls)}>
        <div className={s.row}>
          {/* instrument pill */}
          <div className={s.instrument}>
            <button
              type="button"
              className={s.cycle}
              aria-label="Previous instrument"
              onClick={() => cycle(-1)}
            >
              ‹
            </button>
            <span className={s.instBody}>
              <span className={s.badge}>{instrument.badge}</span>
              <span className={s.instName}>{instrument.short}</span>
            </span>
            <button
              type="button"
              className={s.cycle}
              aria-label="Next instrument"
              onClick={() => cycle(1)}
            >
              ›
            </button>
          </div>

          {/* expiry dropdown */}
          <details className={s.expiry} ref={expiryMenu}>
            <summary aria-label="Select expiry">
              {currentExpiry ? (
                <>
                  {expiryLabel(currentExpiry)}{' '}
                  <span className={s.days}>({daysAwayLabel(currentExpiry)})</span>
                </>
              ) : (
                'Expiry'
              )}
              <span className={s.caret} aria-hidden="true">
                <IconChevronDown />
              </span>
            </summary>
            <div className={s.expiryMenu}>
              {expiries.map((exp) => (
                <button
                  key={exp}
                  type="button"
                  className={cx(s.expiryItem, exp === currentExpiry && s.selected)}
                  onClick={() => pickExpiry(exp)}
                >
                  <span>{expiryLabel(exp)}</span>
                  <span className={s.days}>{daysAwayLabel(exp)}</span>
                </button>
              ))}
              {expiries.length === 0 ? <p className={s.expiryEmpty}>No expiries</p> : null}
            </div>
          </details>

          {/* spot / future / vix */}
          <div className={s.stats}>
            <span className={s.stat}>
              <span className={s.statLabel}>Spot</span>
              <span className={cx(s.statValue, 'mc-numeric')}>
                {spot != null ? formatPrice(spot) : '—'}
              </span>
              {spotChange != null ? (
                <span className={cx(s.statChg, s[pctTone(spotChange)])}>
                  {signedPct(spotChange, 2)}
                </span>
              ) : null}
            </span>
            <span className={s.stat}>
              <span className={s.statLabel}>Future</span>
              <span className={cx(s.statValue, 'mc-numeric')}>
                {future != null ? formatPrice(future) : '—'}
              </span>
            </span>
            <span className={s.stat}>
              <span className={s.statLabel}>VIX</span>
              <span className={cx(s.statValue, 'mc-numeric')}>—</span>
            </span>
          </div>

          {/* live clock */}
          <div className={s.clock}>
            <span className={s.clockIco} aria-hidden="true">
              <IconClock />
            </span>
            <span className="mc-numeric">{clock} IST</span>
            <span className={cx(s.dot, refreshing && s.pulse)} aria-hidden="true" />
          </div>
        </div>

        <div className={cx(s.row, s.row2)}>
          <span className={s.strikesLabel}>Strikes ±ATM:</span>
          {STRIKE_COUNTS.map((c) => (
            <button
              key={String(c)}
              type="button"
              className={cx(s.toggle, strikeCount === c && s.active)}
              onClick={() => setStrikeCount(c)}
            >
              {c === 'All' ? 'All' : `±${c}`}
            </button>
          ))}

          <div className={s.summary}>
            <span className={s.sumChip}>
              <span className={s.sumLabel}>PCR</span>
              <span className={cx(s.sumValue, pcr != null && pcr >= 1 ? s.up : s.down)}>
                {pcr != null ? pcr.toFixed(2) : '—'}
              </span>
            </span>
            <span className={s.sumChip}>
              <span className={s.sumLabel}>Max Pain</span>
              <span className={cx(s.sumValue, s.amber)}>
                {maxPain != null && Number.isFinite(maxPain) ? formatInt(maxPain) : '—'}
              </span>
            </span>
            <span className={s.sumChip}>
              <span className={s.sumLabel}>ATM IV</span>
              <span className={cx(s.sumValue, s.neutral)}>
                {atmIv != null ? `${atmIv.toFixed(1)}%` : '—'}
              </span>
            </span>
          </div>
        </div>
      </section>

      {/* 2. Chain table ------------------------------------------------------ */}
      <section className={cx(s.panel, s.tablePanel)}>
        {/* Focusable because it scrolls: on a phone the 12-column chain is far
            wider than the viewport, and without a tab stop there is no way to
            reach the call-side columns from the keyboard at all. The label is
            what a screen reader announces on landing here.

            The two linters disagree about this. `jsx-a11y/no-noninteractive-
            tabindex` allows a tab stop only on `tabpanel`, while axe's
            `scrollable-region-focusable` fails the page without one. axe is
            testing the rendered result against WCAG 2.1.1, so it wins. */}
        {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
        <div className={s.scroll} tabIndex={0} role="region" aria-label="Option chain">
          <table>
            <thead>
              <tr className={s.headA}>
                <th className={s.callHead} colSpan={5}>
                  Call
                </th>
                <th className={s.centerHead} colSpan={2} />
                <th className={s.putHead} colSpan={5}>
                  Put
                </th>
              </tr>
              <tr className={s.headB}>
                <th className={cx(s.ce, s.l)}>Buildup</th>
                <th className={s.ce}>Volume</th>
                <th className={s.ce}>OI Chg%</th>
                <th className={s.ce}>OI</th>
                <th className={s.ce}>LTP</th>
                <th className={cx(s.center, s.bl)}>Strike ↑</th>
                <th className={cx(s.center, s.br)}>IV</th>
                <th className={s.pe}>LTP</th>
                <th className={s.pe}>OI</th>
                <th className={s.pe}>OI Chg%</th>
                <th className={s.pe}>Volume</th>
                <th className={s.pe}>Buildup</th>
              </tr>
            </thead>
            <tbody>
              {loading
                ? SKELETON_ROWS.map((i) => (
                    <tr className={s.skeletonRow} key={i}>
                      <td colSpan={12}>
                        <span className={s.skeleton} />
                      </td>
                    </tr>
                  ))
                : visible.map((row) => {
                    const isAtm = row.strike === atmStrike;
                    const isMaxPain = maxPain != null && row.strike === maxPain;
                    const ceChg = oiChangePct(row.ce);
                    const peChg = oiChangePct(row.pe);
                    return (
                      <tr key={row.strike} className={cx(isAtm && s.atm)}>
                        {/* CE */}
                        <td className={cx(s.ce, s.l)}>
                          <BuildupBadge buildup={row.ce?.buildup} />
                        </td>
                        <VolCell
                          value={row.ce?.volume}
                          rank={ceRanks.get(row.strike)}
                          top={maxCEVol}
                          side="ce"
                        />
                        <td className={cx(s.ce, s.num, s[pctTone(ceChg)])}>
                          {signedPct(ceChg, 0)}
                        </td>
                        <td className={cx(s.ce, s.num, s.oi)}>
                          <span className={cx(s.oiVal, 'mc-numeric')}>
                            {compactIndian(row.ce?.oi)}
                          </span>
                          <OIBar
                            value={row.ce?.oi}
                            max={maxCallOi}
                            side="ce"
                            className={s.ceTrack}
                          />
                        </td>
                        <td className={cx(s.ce, s.num, s.ltp, s.callLtp, s.brc)}>
                          {ltpText(row.ce)}
                        </td>

                        {/* center */}
                        <td className={cx(s.center, s.strike, s.bl)}>
                          <span className={cx('mc-numeric', s.strikeVal)}>
                            {formatInt(row.strike)}
                          </span>{' '}
                          {isMaxPain ? (
                            <span className={cx(s.tag, s.maxpain)}>Max Pain</span>
                          ) : isAtm ? (
                            <span className={cx(s.tag, s.atmTag)}>ATM</span>
                          ) : null}
                        </td>
                        <td className={cx(s.center, s.iv, s.br)}>{ivText(row.ce, row.pe)}</td>

                        {/* PE */}
                        <td className={cx(s.pe, s.num, s.ltp, s.putLtp)}>{ltpText(row.pe)}</td>
                        <td className={cx(s.pe, s.num, s.oi)}>
                          <span className={cx(s.oiVal, 'mc-numeric')}>
                            {compactIndian(row.pe?.oi)}
                          </span>
                          <OIBar
                            value={row.pe?.oi}
                            max={maxPutOi}
                            side="pe"
                            className={s.peTrack}
                          />
                        </td>
                        <td className={cx(s.pe, s.num, s[pctTone(peChg)])}>
                          {signedPct(peChg, 0)}
                        </td>
                        <VolCell
                          value={row.pe?.volume}
                          rank={peRanks.get(row.strike)}
                          top={maxPEVol}
                          side="pe"
                        />
                        <td className={s.pe}>
                          <BuildupBadge buildup={row.pe?.buildup} />
                        </td>
                      </tr>
                    );
                  })}
            </tbody>
          </table>

          {!loading && visible.length === 0 ? (
            <div className={s.empty}>
              <span className={s.emptyIco} aria-hidden="true">
                <IconChart />
              </span>
              <p className={s.emptyTitle}>No option chain data</p>
              <p className={s.emptyHint}>
                Pick another instrument or expiry, or wait for the next refresh.
              </p>
            </div>
          ) : null}
        </div>
      </section>

      {/* 3. Legend ----------------------------------------------------------- */}
      <section className={cx(s.panel, s.legend)}>
        <span className={s.legItem}>
          <BuildupBadge buildup="Short Covering" /> Short Covering
        </span>
        <span className={s.legItem}>
          <BuildupBadge buildup="Long Build-up" /> Long Build-up
        </span>
        <span className={s.legItem}>
          <BuildupBadge buildup="Short Build-up" /> Short Build-up
        </span>
        <span className={s.legItem}>
          <BuildupBadge buildup="Long Unwinding" /> Long Unwinding
        </span>
        <span className={s.legItem}>
          <span className={cx(s.dot, s.green)} /> Call OI bar
        </span>
        <span className={s.legItem}>
          <span className={cx(s.dot, s.rose)} /> Put OI bar
        </span>
        <span className={s.legItem}>
          <span className={s.volChip}>Vol</span> Top-3 volume — hover for rank
        </span>
        <span className={s.legNote}>Refreshes every 15 s · OI lags exchange by 1–3 min</span>
      </section>
    </div>
  );
}
