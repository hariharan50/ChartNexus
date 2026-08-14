import { useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState, type RefObject } from 'react';
import LwChart, { type Candle, type LwChartHandle } from '$shared/charts/tv/LwChart';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { cx } from '$shared/ui/cx';
import { OI_INSTRUMENTS, REFETCH_MS } from '../../options/open-interest/oi-data';
import { getHistory, INTERVALS, toCandles, toVolume, type HistoryView } from '../analyse-data';
import { buildOverlays } from '../indicators';
import { REPLAY_SPEEDS, type CellConfig, type ReplaySpeed } from '../workspace';
import ChartLegend from './ChartLegend';
import ReplayBar from './ReplayBar';
import s from './ChartCell.module.css';

/**
 * One chart in the workspace: its own history query, indicators and replay head.
 *
 * Configuration is owned by the route (so the shared toolbar can drive whichever
 * cell is focused); everything downstream of it — the fetch, the candle
 * derivation, the replay position — lives here, so a four-up grid is four of
 * these running independently rather than one route juggling four of everything.
 */
interface Props {
  config: CellConfig;
  active: boolean;
  onFocus: () => void;
  onExitReplay: () => void;
  handleRef?: RefObject<LwChartHandle | null> | undefined;
}

export default function ChartCell({ config, active, onFocus, onExitReplay, handleRef }: Props) {
  const theme = useChartTheme();
  const instrument =
    OI_INSTRUMENTS.find((entry) => entry.symbol === config.symbol) ?? OI_INSTRUMENTS[0]!;
  const timeframe = INTERVALS.find((entry) => entry.value === config.interval) ?? INTERVALS[1]!;

  const query = useQuery<HistoryView>({
    queryKey: ['market', 'history', config.symbol, config.interval, timeframe.days],
    queryFn: () => getHistory(config.symbol, config.interval, timeframe.days),
    // Replay is a frozen study of what was loaded; polling under it would shift
    // the bars beneath the playhead.
    refetchInterval: config.replay ? false : REFETCH_MS,
    placeholderData: (previous) => previous
  });

  const view = query.data;
  const allCandles = useMemo(() => toCandles(view), [view]);
  const allVolume = useMemo(() => toVolume(view), [view]);

  // -- replay ---------------------------------------------------------------
  const [head, setHead] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState<ReplaySpeed>(REPLAY_SPEEDS[1]);

  // Entering replay parks the head on the last bar and starts playing from there
  // is wrong — you want to rewind and watch it build, so start at the open.
  useEffect(() => {
    if (config.replay) {
      setHead(0);
      setPlaying(true);
    } else {
      setPlaying(false);
    }
  }, [config.replay]);

  useEffect(() => {
    if (!config.replay || !playing) return;
    const id = window.setInterval(() => {
      setHead((h) => {
        if (h >= allCandles.length - 1) {
          setPlaying(false);
          return h;
        }
        return h + 1;
      });
    }, 1000 / speed);
    return () => window.clearInterval(id);
  }, [config.replay, playing, speed, allCandles.length]);

  const visibleCandles = config.replay ? allCandles.slice(0, head + 1) : allCandles;
  const visibleVolume = config.replay && allVolume ? allVolume.slice(0, head + 1) : allVolume;

  const overlays = useMemo(
    () => buildOverlays(new Set(config.indicators), visibleCandles, visibleVolume),
    [config.indicators, visibleCandles, visibleVolume]
  );

  const [hovered, setHovered] = useState<Candle | null>(null);
  const shownBar = hovered ?? visibleCandles[visibleCandles.length - 1] ?? null;
  const shownVolume = useMemo(() => {
    if (!visibleVolume || !shownBar) return null;
    return visibleVolume.find((bar) => bar.time === shownBar.time)?.value ?? null;
  }, [visibleVolume, shownBar]);

  const source = view?.provenance.source;

  return (
    <div
      className={cx(s.cell, active && s.active)}
      onPointerDown={onFocus}
      role="group"
      aria-label={`${instrument.short} ${config.interval}`}
    >
      <div className={s.plot}>
        {query.isError ? (
          <div className={s.banner} role="alert">
            <span>Couldn’t load {instrument.short}.</span>
            <button type="button" onClick={() => void query.refetch()}>
              Retry
            </button>
          </div>
        ) : allCandles.length === 0 ? (
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
              candles={visibleCandles}
              volume={visibleVolume}
              overlays={overlays}
              theme={theme}
              type={config.chartType}
              onHoverBar={setHovered}
              handleRef={handleRef}
              resetKey={`${config.symbol}:${config.interval}:${config.chartType}`}
              className={s.chart}
            />
            {config.replay ? (
              <ReplayBar
                head={head}
                total={allCandles.length}
                playing={playing}
                speed={speed}
                onHead={(h) => {
                  setPlaying(false);
                  setHead(h);
                }}
                onPlaying={setPlaying}
                onSpeed={setSpeed}
                onExit={onExitReplay}
              />
            ) : null}
          </>
        )}
      </div>

      <div className={s.caption}>
        <span>
          {timeframe.label} · {allCandles.length} candles
          {source && source !== 'live' ? (
            <>
              {' · '}
              <span className={s.provenance}>
                {source === 'mock' ? 'simulated data' : 'cached data'}
              </span>
            </>
          ) : null}
        </span>
        <span
          className={cx(s.dot, query.isFetching && !config.replay && s.pulse)}
          aria-hidden="true"
        />
      </div>
    </div>
  );
}
