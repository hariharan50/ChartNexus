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
  // Per-strike width. The wrapper scrolls horizontally when the ladder does not
  // fit, and because the y-axis is painted on the same canvas it scrolls away
  // with everything else — leaving the OI scale showing one clipped character.
  // 50px keeps the default ±10 view (21 strikes) inside a normal window so that
  // never happens; ±20 still scrolls, which no per-bar width can avoid.
  const minWidth = Math.max(560, bars.length * 50);

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
