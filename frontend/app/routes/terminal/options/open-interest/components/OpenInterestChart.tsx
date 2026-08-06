import { useMemo } from 'react';
import EChart from '$shared/charts/EChart';
import { buildOpenInterestOption } from '$shared/charts/options/open-interest';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { CALL_COLOR, fmtOi, fmtSigned, PUT_COLOR, type OiBar, type OiMode } from '../oi-data';
import s from './OpenInterestChart.module.css';

interface Props {
  bars: OiBar[];
  mode: OiMode;
  spot: number;
  maxPain: number;
  showLot: boolean;
  lotSize: number;
  showTooltip: boolean;
  openLabel: string;
  nowLabel: string;
}

/**
 * Chart chrome — axes, grid, tooltip, markers — comes from `--mc-*` tokens, so
 * it follows all four themes.
 *
 * The Svelte version picked from two hard-coded palettes off an `isDark`
 * boolean, which collapsed `warm` onto the light set and `terminal` onto the
 * dark one. `warm` is a cream surface, so it was being drawn with light-grey
 * axis text on near-white: legible only by accident.
 *
 * Call and Put stay on the Open Interest tool's own palette (`oi-data.ts`)
 * rather than `--mc-bullish`/`--mc-bearish`. They are a domain signal, not
 * chrome — the legend swatches, the donuts and the table all use these exact
 * two colours, and they read correctly against every theme surface.
 */
export default function OpenInterestChart({
  bars,
  mode,
  spot,
  maxPain,
  showLot,
  lotSize,
  showTooltip,
  openLabel,
  nowLabel
}: Props) {
  const theme = useChartTheme();
  const minWidth = Math.max(560, bars.length * 58);

  const option = useMemo(
    () =>
      buildOpenInterestOption(
        {
          bars,
          mode,
          spot,
          maxPain,
          callColor: CALL_COLOR,
          putColor: PUT_COLOR,
          showTooltip,
          formatOi: (value) => fmtOi(value, showLot, lotSize),
          formatSigned: (value) => fmtSigned(value, showLot, lotSize),
          openLabel,
          nowLabel
        },
        theme
      ),
    [bars, mode, spot, maxPain, showTooltip, showLot, lotSize, openLabel, nowLabel, theme]
  );

  return (
    <div className={s.scroll}>
      {/* Toggling contracts/lots changes what the axis formatter means, and a
          merge cannot retire a formatter — so it forces a rebuild. */}
      <EChart
        option={option}
        resetKey={showLot ? 'lot' : 'contracts'}
        className={s.chart}
        style={{ minWidth: `${minWidth}px` }}
      />
    </div>
  );
}
