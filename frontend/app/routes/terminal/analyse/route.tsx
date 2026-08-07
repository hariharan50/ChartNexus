import { useQuery } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import LwChart, {
  type Candle,
  type ChartType,
  type LwChartHandle
} from '$shared/charts/tv/LwChart';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { cx } from '$shared/ui/cx';
import {
  clockLabel,
  dateLabel,
  freshnessLabel,
  OI_INSTRUMENTS,
  REFETCH_MS,
  STALE_AFTER_MS
} from '../options/open-interest/oi-data';
import ChartLegend from './components/ChartLegend';
import SymbolPicker from './components/SymbolPicker';
import TopToolbar from './components/TopToolbar';
import {
  getHistory,
  INTERVALS,
  toCandles,
  toVolume,
  type HistoryView,
  type Interval
} from './analyse-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Analyse · MarketCompass' }];

export default function Analyse() {
  const [symbol, setSymbol] = useState(OI_INSTRUMENTS[0]!.symbol);
  const [interval, setInterval] = useState<Interval>('5m');
  const [chartType, setChartType] = useState<ChartType>('candle');
  const [picking, setPicking] = useState(false);
  const [hovered, setHovered] = useState<Candle | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const theme = useChartTheme();

  const workspace = useRef<HTMLDivElement>(null);
  const chart = useRef<LwChartHandle | null>(null);

  const instrument = OI_INSTRUMENTS.find((entry) => entry.symbol === symbol) ?? OI_INSTRUMENTS[0]!;
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

  // The legend reads the hovered bar, and the newest one whenever the pointer
  // is off the plot — which is most of the time.
  const shownBar = hovered ?? candles[candles.length - 1] ?? null;
  const shownVolume = useMemo(() => {
    if (!volume || !shownBar) return null;
    return volume.find((bar) => bar.time === shownBar.time)?.value ?? null;
  }, [volume, shownBar]);

  // -- fullscreen -----------------------------------------------------------
  useEffect(() => {
    function onChange() {
      setIsFullscreen(document.fullscreenElement === workspace.current);
    }
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);

  const toggleFullscreen = useCallback(() => {
    if (document.fullscreenElement) void document.exitFullscreen();
    else void workspace.current?.requestFullscreen().catch(() => undefined);
  }, []);

  const snapshot = useCallback(() => {
    const canvas = chart.current?.screenshot();
    if (!canvas) return;
    const link = document.createElement('a');
    link.download = `${instrument.symbol}-${interval}.png`;
    link.href = canvas.toDataURL('image/png');
    link.click();
  }, [instrument.symbol, interval]);

  // -- live clock -----------------------------------------------------------
  // `null` until mounted, not `Date.now()`. Seeding it during render puts the
  // server's clock in the HTML and the browser's in the first paint, which is a
  // guaranteed hydration text mismatch — React then throws away and re-renders
  // the tree, and the console error buries anything real.
  const [now, setNow] = useState<number | null>(null);
  useEffect(() => {
    setNow(Date.now());
    const tick = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(tick);
  }, []);

  const updatedAt = query.dataUpdatedAt;
  const isStale = now !== null && updatedAt > 0 && now - updatedAt > STALE_AFTER_MS;
  const source = view?.provenance.source;

  return (
    <div ref={workspace} className={s.workspace}>
      <TopToolbar
        interval={interval}
        onInterval={setInterval}
        symbol={instrument.short}
        onOpenSymbols={() => setPicking(true)}
        chartType={chartType}
        onChartType={setChartType}
        onSnapshot={snapshot}
        onFullscreen={toggleFullscreen}
        isFullscreen={isFullscreen}
      />

      <div className={s.body}>
        <div className={s.plot}>
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
            <>
              <ChartLegend
                symbol={instrument.short}
                badge={instrument.badge}
                bar={shownBar}
                volume={shownVolume}
              />
              <LwChart
                candles={candles}
                volume={volume}
                theme={theme}
                type={chartType}
                onHoverBar={setHovered}
                handleRef={chart}
                className={s.chart}
              />
            </>
          )}
        </div>

        <div className={s.status}>
          <span className={s.caption}>
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
          </span>
          <span className={cx(s.live, isStale && s.stale)}>
            <span className={cx(s.dot, query.isFetching && s.pulse)} />
            {now === null ? null : (
              <>
                <span>
                  {dateLabel(now)}, {clockLabel(now)} IST
                </span>
                <span className={s.sep} aria-hidden="true">
                  ·
                </span>
                <span>{freshnessLabel(updatedAt, now)}</span>
              </>
            )}
          </span>
        </div>
      </div>

      {picking ? (
        <SymbolPicker
          instruments={OI_INSTRUMENTS}
          selected={instrument.symbol}
          onPick={setSymbol}
          onClose={() => setPicking(false)}
        />
      ) : null}
    </div>
  );
}
