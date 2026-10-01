import { useMemo, useState } from 'react';
import { useFuturesBoardQuery } from '$contexts/futures-analytics/queries';
import type { FuturesRow } from '$contexts/futures-analytics/types';
import EChart from '$shared/charts/EChart';
import {
  buildFuturesHeatmapOption,
  type HeatmapCell
} from '$shared/charts/options/futures-heatmap';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import DataSourceBadge from '$shared/ui/DataSourceBadge';
import Select from '$shared/ui/Select';
import { cx } from '$shared/ui/cx';
import IconGrid from '$shared/ui/icons/IconGrid';
import ExpiryPicker from './components/ExpiryPicker';
import { ReplayToggle, SessionStatus } from './components/SessionHeader';
import {
  applyFilter,
  filterCounts,
  HEATMAP_FILTERS,
  SIZE_OPTIONS,
  type HeatmapFilterId,
  type HeatmapSizeId
} from './heatmap-data';
import { stateMeta, toNumber } from './stocks-data';
import s from './heatmap.module.css';
import type { Route } from './+types/heatmap';

export const meta: Route.MetaFunction = () => [
  { title: 'Future Heatmap · Future Lab · MarketCompass' }
];

/** Matches the board's own poll, so the ring counts down to a real refresh. */
const REFRESH_SECONDS = 15;

const EMPTY: FuturesRow[] = [];

const PENDING_HISTORY =
  'Historical replay needs a stored board history, which is not captured yet.';

export default function FutureHeatmap() {
  const [filter, setFilter] = useState<HeatmapFilterId>('all');
  const [size, setSize] = useState<HeatmapSizeId>('turnover');
  const theme = useChartTheme();

  const [series, setSeries] = useState(0);

  const board = useFuturesBoardQuery({ kind: 'stock', series });

  const rows = useMemo(() => board.data?.rows ?? EMPTY, [board.data]);
  // Counts describe the whole board; the chips have to say what they *would*
  // show, not what the current selection already shows.
  const counts = useMemo(() => filterCounts(rows), [rows]);
  const visible = useMemo(() => applyFilter(rows, filter), [rows, filter]);

  const option = useMemo(() => {
    const cells: HeatmapCell[] = visible.map((row) => ({
      symbol: row.symbol,
      name: row.name,
      sector: row.sector,
      changePercent: toNumber(row.price_change_percent),
      // Turnover, not volume: a hundred lots of a ₹40,000 contract is not the
      // same size of trade as a hundred lots of a ₹15 one.
      turnover: (toNumber(row.price) ?? 0) * (row.volume ?? 0),
      volume: row.volume,
      openInterest: row.open_interest,
      price: row.price,
      oiChangePercent: toNumber(row.oi_change_percent),
      sentiment: stateMeta(row.state).label
    }));
    return buildFuturesHeatmapOption(cells, theme, { layout: 'flat', size });
  }, [visible, theme, size]);

  return (
    <div className={s.page}>
      <header className={s.header}>
        <h1 className={s.title}>
          <span className={s.titleIco} aria-hidden="true">
            <IconGrid />
          </span>
          Future Heatmap
        </h1>
        <div className={s.headerRight}>
          {/* Shown because the design has it, disabled because replaying the
              *board* needs a per-frame universe snapshot, which the capture
              worker does not yet assemble. */}
          <ReplayToggle on={false} disabled reason={PENDING_HISTORY} />
          <SessionStatus
            intervalSeconds={REFRESH_SECONDS}
            active={!board.isFetching}
            updatedAt={board.dataUpdatedAt}
          />
        </div>
      </header>

      <div className={s.modeBar}>
        <div className={s.segmented} role="group" aria-label="Data mode">
          <button type="button" className={cx(s.segment, s.segmentOn)} aria-pressed>
            Live
          </button>
          <button type="button" className={s.segment} disabled title={PENDING_HISTORY}>
            Historical
          </button>
        </div>

        <span className={s.label}>Expiry</span>
        <ExpiryPicker
          series={series}
          onSeries={setSeries}
          resolved={board.data?.expiry}
          hasOpenInterest={board.data?.has_open_interest}
          bare
        />

        <div className={s.sizeBy}>
          <span className={s.label}>Size by</span>
          <Select
            className={s.select}
            size="sm"
            value={size}
            ariaLabel="Size cells by"
            onChange={setSize}
            options={SIZE_OPTIONS.map((entry) => ({ value: entry.id, label: entry.label }))}
          />
        </div>

        <span className={s.status}>
          {board.data?.source ? <DataSourceBadge source={board.data.source} /> : null}
        </span>
      </div>

      <div className={s.chips} role="group" aria-label="Filter">
        {HEATMAP_FILTERS.map((entry) => {
          const selected = entry.id === filter;
          return (
            <button
              key={entry.id}
              type="button"
              className={cx(s.chipBtn, selected && s.chipOn)}
              aria-pressed={selected}
              onClick={() => setFilter(entry.id)}
            >
              {entry.label}
              <span className={s.chipCount}>{counts[entry.id] ?? 0}</span>
            </button>
          );
        })}
      </div>

      {board.isError ? (
        <p className={s.error}>The heatmap could not be loaded.</p>
      ) : board.data === undefined ? (
        <p className={s.placeholder}>Loading the board…</p>
      ) : visible.length === 0 ? (
        <p className={s.placeholder}>No contracts in this state right now.</p>
      ) : (
        <div className={s.chartWrap}>
          <EChart option={option} className={s.chart} resetKey={`${filter}:${size}`} />
        </div>
      )}
    </div>
  );
}
