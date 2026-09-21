import { useMemo } from 'react';
import type { FuturesRow } from '$contexts/futures-analytics/types';
import EChart from '$shared/charts/EChart';
import {
  buildFuturesHeatmapOption,
  type HeatmapCell
} from '$shared/charts/options/futures-heatmap';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { toNumber } from '../stocks-data';
import s from './MoversHeatmap.module.css';

/** The same rows the table shows, as area and colour. */
export default function MoversHeatmap({ rows }: { rows: FuturesRow[] }) {
  const theme = useChartTheme();

  const option = useMemo(() => {
    const cells: HeatmapCell[] = rows.map((row) => ({
      symbol: row.symbol,
      name: row.name,
      sector: row.sector,
      changePercent: toNumber(row.price_change_percent),
      // Turnover, not volume: a hundred lots of a ₹40,000 contract is not the
      // same size of trade as a hundred lots of a ₹15 one.
      turnover: (toNumber(row.price) ?? 0) * (row.volume ?? 0)
    }));
    return buildFuturesHeatmapOption(cells, theme);
  }, [rows, theme]);

  if (rows.length === 0) {
    return <p className={s.empty}>Nothing to map.</p>;
  }

  return (
    <div className={s.wrap}>
      <EChart option={option} className={s.chart} />
    </div>
  );
}
