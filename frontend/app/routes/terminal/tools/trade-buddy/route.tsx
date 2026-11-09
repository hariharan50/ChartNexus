import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useRef, useState } from 'react';
import { cx } from '$shared/ui/cx';
import AlertChannels from './components/AlertChannels';
import AlertFeed from './components/AlertFeed';
import AlertSettings from './components/AlertSettings';
import DeliveryChips from './components/DeliveryChips';
import LevelsCard from './components/LevelsCard';
import SessionCard from './components/SessionCard';
import StaleBanner from './components/StaleBanner';
import WatchlistStrip from './components/WatchlistStrip';
import {
  bandWarning,
  clearLevels,
  DEFAULT_SYMBOL,
  draftFrom,
  emptyDraft,
  feedVerdict,
  fireTestAlert,
  getChannels,
  getEngineState,
  getLevels,
  getSettings,
  getWatchlist,
  REFETCH_MS,
  setLevels,
  setSettings,
  markedNote,
  staleWarning,
  toPayload,
  validateDraft,
  watchableOr,
  type AlertKind,
  type ChannelsResponse,
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

  // The delivery chip is a shortcut to the card that can fix it. Scrolling
  // rather than opening a dialog: the card is on this page, and a modal would
  // hide the levels you were looking at when you noticed the bot was off.
  const deliveryRef = useRef<HTMLDivElement>(null);
  function openDelivery() {
    deliveryRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }

  // "Re-mark" has to leave the cursor somewhere useful. An empty form with no
  // focus is a dead end — the reader has just told the page they want to type.
  const firstPriceRef = useRef<HTMLInputElement>(null);
  function remark() {
    setDraft(emptyDraft());
    setDirty(true);
    setError(null);
    setNotice(null);
    firstPriceRef.current?.focus();
  }

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

  // Same key and same fetcher as the Delivery card's own query, so react-query
  // serves both from one cache entry and one request. Lifting the query out of
  // that card instead would have made the card unusable on its own and bought
  // nothing: the page needs the answer for a chip, the card needs it for a
  // whole flow, and neither is the other's owner.
  const channels = useQuery<ChannelsResponse>({
    queryKey: ['trade-buddy', 'channels'],
    queryFn: getChannels
  });

  // Seed the form from the server once, and never again while the user is
  // mid-edit: the levels poll would otherwise reset a half-typed price.
  useEffect(() => {
    if (marks.data && !dirty) setDraft(draftFrom(marks.data.levels));
  }, [marks.data, dirty]);

  // Re-save the marks exactly as they are. `SetLevels` always stamps the
  // current session and drops the saved watcher states, so "the same six
  // numbers, for today" needs nothing from the API that marking does not
  // already do — and the states it drops described a session that has ended.
  const carry = useMutation({
    mutationFn: () => setLevels(symbol, marks.data?.levels ?? []),
    onSuccess: async () => {
      setDirty(false);
      setError(null);
      setNotice(`Levels carried forward for ${symbol}.`);
      await queryClient.invalidateQueries({ queryKey: ['trade-buddy'] });
    },
    onError: (cause: Error) => setError(cause.message)
  });

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

  // Back to what the server has, not to blank. "Discard" means "forget what I
  // typed", and a form that cleared itself instead would destroy the saved
  // marks in the one gesture whose whole promise is that it changes nothing.
  function discard() {
    setDraft(draftFrom(marks.data?.levels ?? []));
    setDirty(false);
    setError(null);
    setNotice(null);
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
  const telegram = channels.data?.channels.find((channel) => channel.channel === 'telegram');
  const levels = engine.data?.levels ?? [];
  const validation = useMemo(() => validateDraft(draft), [draft]);
  // The saved marks in draft shape, so the table can mark an edited row and
  // Discard has something to restore. Derived from the same query the form is
  // seeded from, so the two cannot disagree about what "saved" means.
  const savedDraft = useMemo(() => draftFrom(marks.data?.levels ?? []), [marks.data]);

  return (
    <div className={s.page}>
      {/* -- the header ------------------------------------------------------
          Two halves: what this page is, and whether it is working. The second
          is not a detail — every number below it is only as trustworthy as
          the answer to "is the feed alive", so it sits at the top right where
          a status belongs rather than in a band of its own. */}
      <header className={s.head}>
        <div className={s.headText}>
          <p className={s.crumb}>Tools / Trade Buddy</p>
          <h1 className={s.title}>Trade Buddy</h1>
          <p className={s.sub}>
            Mark today&apos;s levels and the watcher alerts on approaches, touches, confirmed breaks
            and reclaims.
          </p>
        </div>
        <SessionCard verdict={verdict} state={engine.data} now={now} />
      </header>

      {/* -- the watchlist ---------------------------------------------------
          Doubles as the instrument selector. Three known indices, each with a
          state worth reading, is a job for tabs rather than the searchable
          `InstrumentPicker` the other pages use for two hundred names — but
          the selection still goes through `useSelectedInstrument`, so it
          syncs with them either way. */}
      <WatchlistStrip
        rows={watchlist.data?.instruments ?? []}
        selected={symbol}
        onSelect={pick}
        chips={
          <DeliveryChips telegram={telegram} state={engine.data} onOpenDelivery={openDelivery} />
        }
      />

      {/* The only state in which a quiet phone is correct behaviour rather
          than a fault — and the only banner that carries its own fix. */}
      {staleNote && (
        <StaleBanner
          symbol={symbol}
          markedOn={engine.data?.marked_on}
          onCarryForward={() => carry.mutate()}
          onRemark={remark}
          carrying={carry.isPending}
          canCarry={(marks.data?.levels.length ?? 0) > 0}
        />
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
        {/* Left: the levels, which is what the page is for. `flex: 999` makes
            this take every spare pixel while still being allowed to shrink to
            its 40rem basis — below about 1000px the right column drops under
            it with no media query, because the basis sum stops fitting. */}
        <div className={s.main}>
          <LevelsCard
            symbol={symbol}
            draft={draft}
            saved={savedDraft}
            live={levels}
            price={engine.data?.last_price ?? null}
            bands={engine.data?.bands}
            markedOn={engine.data?.marked_on}
            armed={marked !== null}
            stale={!!engine.data?.levels_stale}
            dailyCap={settings.data?.daily_alert_cap ?? 3}
            dirty={dirty}
            validation={validation}
            saving={save.isPending}
            clearing={wipe.isPending}
            onChange={update}
            onSave={submit}
            onDiscard={discard}
            onClear={() => wipe.mutate()}
            firstPriceRef={firstPriceRef}
          />
        </div>

        {/* Right: everything that is about the alerts rather than the levels.
            These were full-width blocks below the fold, which gave the most
            screen to the two things set up once and never touched again. */}
        <div className={s.side}>
          {/* First in the column: the only panel here that changes during the
              session, and the answer to "what did I miss". */}
          <AlertFeed symbol={symbol} />

          <AlertSettings
            settings={settings.data}
            saving={saveSettings.isPending}
            onSave={(overrides) => saveSettings.mutate(overrides)}
          />
          <div ref={deliveryRef}>
            <AlertChannels
              symbol={symbol}
              testKind={testKind}
              onTestKindChange={setTestKind}
              onTest={() => test.mutate()}
              testing={test.isPending}
              canTest={levels.length > 0}
              whatsappUsed={engine.data?.whatsapp_used}
              whatsappLimit={engine.data?.whatsapp_limit}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
