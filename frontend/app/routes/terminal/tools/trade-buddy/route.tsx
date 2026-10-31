import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { cx } from '$shared/ui/cx';
import Button from '$shared/ui/Button';
import Select from '$shared/ui/Select';
import AlertChannels from './components/AlertChannels';
import AlertSettings from './components/AlertSettings';
import LevelLadder from './components/LevelLadder';
import WatchlistStrip from './components/WatchlistStrip';
import {
  bandWarning,
  clearLevels,
  DEFAULT_SYMBOL,
  draftFrom,
  emptyDraft,
  FEED_COPY,
  feedVerdict,
  fireTestAlert,
  formatPrice,
  formatTime,
  getEngineState,
  getLevels,
  getSettings,
  getWatchlist,
  hasFlipped,
  REFETCH_MS,
  secondsSince,
  setLevels,
  setSettings,
  markedNote,
  staleWarning,
  stateLook,
  toPayload,
  validateDraft,
  watchableOr,
  type AlertKind,
  type DraftLevel,
  type EngineState,
  type LevelsResponse,
  type Overrides,
  type Settings,
  type Watchable,
  type WatchlistResponse
} from './trade-buddy-data';
import s from './route.module.css';
import type { Route } from './+types/route';
import { useSelectedInstrument } from '$contexts/instrument-catalog/selected-instrument';

export const meta: Route.MetaFunction = () => [{ title: 'Trade Buddy · Tools' }];

const TEST_KINDS: { value: AlertKind; label: string }[] = [
  { value: 'touched', label: 'Touched (Telegram only)' },
  { value: 'approaching', label: 'Approaching (Telegram only)' },
  { value: 'break_confirmed', label: 'Break confirmed (also WhatsApp)' }
];

/**
 * Trade Buddy — mark the morning's levels, then watch what the engine makes of them.
 *
 * Two halves, in the order the day runs: the marks go in before the open, and
 * the live panel is what you read during the session. The status strip sits
 * above both because it answers the question that makes the rest trustworthy —
 * is the watcher actually running, or is this a quiet market? Those look
 * identical from the outside, which is the premise the whole feature rests on.
 */
export default function TradeBuddy() {
  const queryClient = useQueryClient();
  // Shared with the rest of the terminal so switching index here follows you
  // to the option chain and back. Constrained, because that picker also
  // offers stocks and this page watches three indices.
  const [globalSymbol, selectInstrument] = useSelectedInstrument();
  const symbol = watchableOr(globalSymbol, DEFAULT_SYMBOL);

  function pick(next: Watchable) {
    setDirty(false);
    setError(null);
    setNotice(null);
    selectInstrument(next);
  }

  const [draft, setDraft] = useState<DraftLevel[]>(emptyDraft);
  const [dirty, setDirty] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [testKind, setTestKind] = useState<AlertKind>('touched');

  // Re-rendered on a timer so "last tick 94s ago" ages even when the poll
  // returns an unchanged payload. Without this the staleness badge would only
  // update when something else happened to change.
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1_000);
    return () => clearInterval(id);
  }, []);

  const marks = useQuery<LevelsResponse>({
    queryKey: ['trade-buddy', 'levels', symbol],
    queryFn: () => getLevels(symbol)
  });

  const engine = useQuery<EngineState>({
    queryKey: ['trade-buddy', 'state', symbol],
    queryFn: () => getEngineState(symbol),
    refetchInterval: REFETCH_MS
  });

  const settings = useQuery<Settings>({
    queryKey: ['trade-buddy', 'settings', symbol],
    queryFn: () => getSettings(symbol)
  });

  const watchlist = useQuery<WatchlistResponse>({
    queryKey: ['trade-buddy', 'watchlist'],
    queryFn: getWatchlist,
    refetchInterval: REFETCH_MS
  });

  // Seed the form from the server once, and never again while the user is
  // mid-edit: the levels poll would otherwise reset a half-typed price.
  useEffect(() => {
    if (marks.data && !dirty) setDraft(draftFrom(marks.data.levels));
  }, [marks.data, dirty]);

  const save = useMutation({
    mutationFn: () => setLevels(symbol, toPayload(draft)),
    onSuccess: async (saved) => {
      setDirty(false);
      setError(null);
      setNotice(`Saved ${saved.levels.length} level${saved.levels.length === 1 ? '' : 's'}.`);
      await queryClient.invalidateQueries({ queryKey: ['trade-buddy'] });
    },
    onError: (cause: Error) => setError(cause.message)
  });

  const wipe = useMutation({
    mutationFn: () => clearLevels(symbol),
    onSuccess: async () => {
      setDraft(emptyDraft());
      setDirty(false);
      setError(null);
      setNotice('Levels cleared.');
      await queryClient.invalidateQueries({ queryKey: ['trade-buddy'] });
    },
    onError: (cause: Error) => setError(cause.message)
  });

  const saveSettings = useMutation({
    mutationFn: (overrides: Overrides) => setSettings(symbol, overrides),
    onSuccess: async () => {
      setError(null);
      setNotice('Alert settings saved.');
      await queryClient.invalidateQueries({ queryKey: ['trade-buddy'] });
    },
    onError: (cause: Error) => setError(cause.message)
  });

  const test = useMutation({
    mutationFn: () => fireTestAlert(symbol, testKind),
    onSuccess: (result) => {
      setError(null);
      setNotice(`Test alert sent: ${result.rendered}`);
    },
    onError: (cause: Error) => setError(cause.message)
  });

  function update(index: number, price: string) {
    setDirty(true);
    setNotice(null);
    setDraft((rows) => rows.map((row, i) => (i === index ? { ...row, price } : row)));
  }

  function submit() {
    const problem = validateDraft(draft);
    if (problem) {
      setError(problem);
      return;
    }
    setError(null);
    save.mutate();
  }

  const verdict = feedVerdict(engine.data, now);
  // Stale levels rank above unscaled bands: the first stops alerts
  // entirely, the second only changes their size.
  const staleNote = staleWarning(engine.data);
  const marked = markedNote(engine.data);
  const bandNote = staleNote ? null : bandWarning(engine.data?.bands);
  const silence = secondsSince(engine.data?.last_tick_at ?? null, now);
  const levels = engine.data?.levels ?? [];
  const validation = useMemo(() => validateDraft(draft), [draft]);
  const busy = save.isPending || wipe.isPending;

  return (
    <div className={s.page}>
      <header className={s.head}>
        <h1 className={s.title}>Trade Buddy</h1>
        <p className={s.sub}>
          Mark today&apos;s levels; the watcher compares live price against them and alerts on
          approaches, touches, confirmed breaks and reclaims.
        </p>
      </header>

      {/* -- the watchlist ---------------------------------------------------
          Doubles as the instrument selector. Three known indices, each with a
          state worth reading, is a job for tabs rather than the searchable
          `InstrumentPicker` the other pages use for two hundred names — but
          the selection still goes through `useSelectedInstrument`, so it
          syncs with them either way. */}
      <WatchlistStrip rows={watchlist.data?.instruments ?? []} selected={symbol} onSelect={pick} />

      {/* -- status strip ----------------------------------------------------
          First, and deliberately loud. Every number below it is only as
          trustworthy as the answer to "is the feed alive". */}
      <section className={s.strip} aria-label="Watcher status">
        <div className={cx(s.verdict, s[`verdict_${verdict}`])}>
          <span className={s.verdictDot} aria-hidden="true" />
          <div>
            <p className={s.verdictLabel}>{FEED_COPY[verdict].label}</p>
            <p className={s.verdictDetail}>{FEED_COPY[verdict].detail}</p>
          </div>
        </div>

        <dl className={s.facts}>
          <div className={s.fact}>
            <dt>Last price</dt>
            <dd className={s.factStrong}>
              {engine.data?.last_price != null ? formatPrice(engine.data.last_price) : '—'}
            </dd>
          </div>
          <div className={s.fact}>
            <dt>Last tick</dt>
            <dd>
              {formatTime(engine.data?.last_tick_at ?? null)}
              {silence !== null && <span className={s.ago}> · {silence}s ago</span>}
            </dd>
          </div>
          <div className={s.fact}>
            <dt>WhatsApp budget</dt>
            <dd>
              {engine.data ? `${engine.data.whatsapp_used} / ${engine.data.whatsapp_limit}` : '—'}
              <span className={s.ago}> · 4h window</span>
            </dd>
          </div>
        </dl>
      </section>

      {/* Loudest banner on the page: it is the only state in which a quiet
          phone is correct behaviour rather than a fault. */}
      {staleNote && (
        <p className={cx(s.banner, s.bannerError)} role="status">
          {staleNote}
        </p>
      )}

      {/* A degraded band set changes what every alert on this instrument
          means, so it is stated rather than left to be inferred from the
          numbers. */}
      {bandNote && (
        <p className={cx(s.banner, s.bannerWarn)} role="status">
          {bandNote}
        </p>
      )}

      {(error || notice) && (
        <p className={cx(s.banner, error ? s.bannerError : s.bannerOk)} role="status">
          {error ?? notice}
        </p>
      )}

      <div className={s.columns}>
        {/* -- the marks --------------------------------------------------- */}
        <section className={s.panel} aria-labelledby="tb-marks">
          <h2 id="tb-marks" className={s.panelTitle}>
            Today&apos;s levels · <span className={s.panelSymbol}>{symbol}</span>
          </h2>
          <p className={s.panelNote}>
            Leave a row blank to skip it. Saving replaces the marks and resets the live state, so
            the session starts clean against the new prices.
          </p>

          <div className={s.form}>
            {draft.map((row, index) => (
              <div key={row.label} className={s.row}>
                <span className={cx(s.rowLabel, s[`role_${row.role}`])}>{row.label}</span>
                <input
                  className={s.input}
                  type="number"
                  inputMode="decimal"
                  step="0.05"
                  min="0"
                  placeholder="—"
                  aria-label={`${row.label} price`}
                  value={row.price}
                  onChange={(event) => update(index, event.target.value)}
                />
                <span className={s.rowRole}>{row.role}</span>
              </div>
            ))}
          </div>

          <div className={s.actions}>
            <Button onClick={submit} loading={save.isPending} disabled={busy || !!validation}>
              Save levels
            </Button>
            <Button variant="ghost" onClick={() => wipe.mutate()} loading={wipe.isPending}>
              Clear
            </Button>
          </div>
          {validation && dirty && <p className={s.hint}>{validation}</p>}
        </section>

        {/* -- the live watch ---------------------------------------------- */}
        <section className={s.panel} aria-labelledby="tb-live">
          <h2 id="tb-live" className={s.panelTitle}>
            Live watch · <span className={s.panelSymbol}>{symbol}</span>
          </h2>
          {/* Guarded on `bands`, not on `engine.data`. A backend that predates
              this field answers 200 with a payload that simply lacks it, and
              reaching through it crashed the whole page — a version skew
              during a deploy must degrade to a missing line, never to a white
              screen. */}
          {marked && (
            <p className={s.panelNote}>
              <span className={s.marked}>{marked}</span>
            </p>
          )}

          {engine.data?.bands && (
            <p className={s.panelNote}>
              Bands: touch {engine.data.bands.touch} · approach {engine.data.bands.approach} ·
              buffer {engine.data.bands.break_buffer} pts
              {engine.data.bands.atr !== null
                ? ` — scaled from ATR ${engine.data.bands.atr}`
                : ' — unscaled point defaults'}
            </p>
          )}

          {levels.length === 0 ? (
            <p className={s.empty}>
              No levels marked yet. Save some on the left and the watcher will pick them up on its
              next tick.
            </p>
          ) : (
            <>
              <LevelLadder levels={levels} price={engine.data?.last_price ?? null} />

              <table className={s.table}>
                <caption className={s.srOnly}>
                  Each marked level, its current role, and what the watcher has seen
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Level</th>
                    <th scope="col">Price</th>
                    <th scope="col">Acting as</th>
                    <th scope="col">State</th>
                    <th scope="col" className={s.numeric}>
                      Alerts left
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {levels.map((level) => {
                    const look = stateLook(level.state);
                    const flipped = hasFlipped(level);
                    return (
                      <tr key={level.label}>
                        <th scope="row" className={s.cellLabel}>
                          {level.label}
                        </th>
                        <td className={s.numeric}>{formatPrice(level.level_price)}</td>
                        <td>
                          <span className={cx(s.roleTag, s[`role_${level.role}`])}>
                            {level.role}
                          </span>
                          {flipped && <span className={s.flip}> flipped</span>}
                        </td>
                        <td>
                          {/* Glyph + word, never colour alone: this has to survive
                              greyscale, colour-vision deficiency and forced-colours. */}
                          <span className={cx(s.state, s[`tone_${look.tone}`])}>
                            <span aria-hidden="true">{look.glyph}</span> {look.label}
                          </span>
                        </td>
                        <td className={s.numeric}>{level.alerts_remaining}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </>
          )}

          <div className={s.testRow}>
            <Select
              className={s.testSelect}
              value={testKind}
              ariaLabel="Test alert type"
              options={TEST_KINDS}
              onChange={setTestKind}
            />
            <Button
              variant="secondary"
              onClick={() => test.mutate()}
              loading={test.isPending}
              disabled={levels.length === 0}
            >
              Send test alert
            </Button>
          </div>
          <p className={s.panelNote}>
            A test goes through the real notifiers and the real channel policy, so a confirmed-break
            test also spends one WhatsApp message.
          </p>
        </section>
      </div>

      {/* Full width, not a second two-column row. Side by side, the six
          threshold fields were forced into a single tall stack in a ~22rem
          column while the channel panel sat short and wide beside it — two
          mismatched heights and a large void. Given the whole width, the
          fields wrap into rows and both panels end where their content does. */}
      <AlertSettings
        settings={settings.data}
        saving={saveSettings.isPending}
        onSave={(overrides) => saveSettings.mutate(overrides)}
      />
      <AlertChannels />
    </div>
  );
}
