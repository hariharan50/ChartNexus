import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import LwChart from '$shared/charts/tv/LwChart';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { cx } from '$shared/ui/cx';
import IconChart from '$shared/ui/icons/IconChart';
import {
  clockLabel,
  dateLabel,
  freshnessLabel,
  OI_INSTRUMENTS,
  REFETCH_MS,
  STALE_AFTER_MS
} from '../options/open-interest/oi-data';
import {
  fmtPrice,
  getHistory,
  INTERVALS,
  summarise,
  toCandles,
  toVolume,
  type HistoryView,
  type Interval
} from './analyse-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Analyse · MarketCompass' }];

export default function Analyse() {
  const [instIdx, setInstIdx] = useState(0);
  const [interval, setInterval] = useState<Interval>('5m');
  const theme = useChartTheme();

  const instrument = OI_INSTRUMENTS[instIdx] ?? OI_INSTRUMENTS[0]!;
  const timeframe = INTERVALS.find((entry) => entry.value === interval) ?? INTERVALS[1]!;

  const query = useQuery<HistoryView>({
    queryKey: ['market', 'history', instrument.symbol, interval, timeframe.days],
    queryFn: () => getHistory(instrument.symbol, interval, timeframe.days),
    refetchInterval: REFETCH_MS,
    // The drawn window is stable across a poll, so keeping the old candles up
    // while the new ones arrive avoids the chart blanking every fifteen seconds.
    placeholderData: (previous) => previous
  });

  const view = query.data;
  const candles = useMemo(() => toCandles(view), [view]);
  const volume = useMemo(() => toVolume(view), [view]);
  const summary = useMemo(() => summarise(candles), [candles]);

  // -- live clock -----------------------------------------------------------
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(tick);
  }, []);

  const updatedAt = query.dataUpdatedAt;
  const isStale = updatedAt > 0 && now - updatedAt > STALE_AFTER_MS;
  const source = view?.provenance.source;

  return (
    <div className={s.page}>
      <section className={s.panel}>
        <div className={s.top}>
          <div className={s.identity}>
            <span className={s.badge}>{instrument.badge}</span>
            <div>
              <h2 className={s.title}>
                <span className={s.ico} aria-hidden="true">
                  <IconChart />
                </span>{' '}
                {instrument.short}
              </h2>
              {summary ? (
                <p className={s.quote}>
                  <span className={s.last}>{fmtPrice(summary.last)}</span>
                  <span className={cx(s.change, summary.change >= 0 ? s.up : s.down)}>
                    {summary.change >= 0 ? '+' : ''}
                    {fmtPrice(summary.change)} ({summary.changePct >= 0 ? '+' : ''}
                    {summary.changePct.toFixed(2)}%)
                  </span>
                  {/* Named, because this is the range's move rather than the
                      day's — the two differ on every timeframe but 1D. */}
                  <span className={s.overRange}>over the drawn range</span>
                </p>
              ) : null}
            </div>
          </div>

          <div className={s.controls}>
            <span className={s.cyclers}>
              <button
                type="button"
                aria-label="Previous instrument"
                onClick={() =>
                  setInstIdx((i) => (i - 1 + OI_INSTRUMENTS.length) % OI_INSTRUMENTS.length)
                }
              >
                ‹
              </button>
              <button
                type="button"
                aria-label="Next instrument"
                onClick={() => setInstIdx((i) => (i + 1) % OI_INSTRUMENTS.length)}
              >
                ›
              </button>
            </span>

            <div className={s.pills} role="group" aria-label="Interval">
              {INTERVALS.map((entry) => (
                <button
                  key={entry.value}
                  type="button"
                  className={cx(s.pill, interval === entry.value && s.active)}
                  aria-pressed={interval === entry.value}
                  onClick={() => setInterval(entry.value)}
                >
                  {entry.label}
                </button>
              ))}
            </div>

            <span className={cx(s.live, isStale && s.stale)}>
              <span className={cx(s.dot, query.isFetching && s.pulse)} />
              <span>
                {dateLabel(now)}, {clockLabel(now)} IST
              </span>
              <span className={s.sep} aria-hidden="true">
                ·
              </span>
              <span>{freshnessLabel(updatedAt, now)}</span>
            </span>
          </div>
        </div>

        {query.isError ? (
          <div className={s.banner} role="alert">
            <span>Couldn’t load price history.</span>
            <button type="button" onClick={() => void query.refetch()}>
              Retry
            </button>
          </div>
        ) : candles.length === 0 ? (
          <p className={s.empty}>{query.isPending ? 'Loading candles…' : 'No candles yet.'}</p>
        ) : (
          <LwChart candles={candles} volume={volume} theme={theme} className={s.chart} />
        )}

        <p className={s.caption}>
          {timeframe.label} bars over {timeframe.days} trading{' '}
          {timeframe.days === 1 ? 'day' : 'days'} · {candles.length} candles
          {volume === undefined ? ' · no volume (an index has no turnover of its own)' : ''}
          {source && source !== 'live' ? (
            <>
              {' · '}
              {/* Provenance is on screen for the same reason the API insists on
                  sending it: cached and simulated bars look exactly like live
                  ones, and acting on the difference is the reader's call. */}
              <span className={s.provenance}>
                {source === 'mock' ? 'simulated data' : 'cached data'}
              </span>
            </>
          ) : null}
        </p>
      </section>
    </div>
  );
}
