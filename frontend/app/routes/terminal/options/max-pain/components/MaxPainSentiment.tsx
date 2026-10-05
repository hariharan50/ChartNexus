import { useMemo } from 'react';
import EChart from '$shared/charts/EChart';
import { buildZonedGaugeOption } from '$shared/charts/options/zoned-gauge';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import type { ChartTheme } from '$shared/charts/theme/types';
import type { MaxPainBias, MaxPainZone } from '../max-pain-data';
import s from './MaxPainSentiment.module.css';

/**
 * How the market sits relative to the level that hurts most option holders.
 *
 * TradingView's Summary dial rather than the Open Interest tool's
 * `SentimentDonut`: a ring shows magnitude only, and the reading here is signed
 * — spot *above* max pain and spot *below* it are opposite calls, not stronger
 * and weaker versions of the same one.
 */
interface Props {
  bias: MaxPainBias;
  maxPain: number;
  spot: number;
}

/**
 * The colour a zone's name is written in.
 *
 * Theme roles, not the reference's literal blue and red: `--cn-accent` and
 * `--cn-bearish` are already tuned per theme, and the verdict is 16px bold —
 * ordinary text as far as contrast is concerned, so it owes a full 4.5:1 on all
 * four themes. A hardcoded `#2962ff` clears that on white and fails it on the
 * warm theme.
 *
 * The arc's gradient keeps the reference's red-to-indigo ramp: it is a
 * graphical element, and the zone it lands in is named in words beside it.
 */
function zoneColor(zone: MaxPainZone, theme: ChartTheme): string {
  if (zone === 'Strong sell' || zone === 'Sell') return theme.put;
  if (zone === 'Buy' || zone === 'Strong buy') return theme.accent;
  return theme.axis;
}

export default function MaxPainSentiment({ bias, maxPain, spot }: Props) {
  const theme = useChartTheme();
  const color = zoneColor(bias.label, theme);

  const option = useMemo(
    () =>
      buildZonedGaugeOption(
        {
          position: bias.position,
          readout: `${bias.gapPct >= 0 ? '+' : ''}${bias.gapPct.toFixed(2)}%`,
          zone: bias.label,
          zoneColor: color
        },
        theme
      ),
    [bias.position, bias.gapPct, bias.label, color, theme]
  );

  return (
    <div className={s.panel}>
      <div className={s.gaugeWrap}>
        <h3 className={s.summary}>Summary</h3>
        <EChart option={option} className={s.gauge} />
        {/* The gauge's own labels live on a canvas, so they are invisible to a
            screen reader and unsearchable. The verdict is repeated here in
            markup — the one place it must always be readable. */}
        <p className={s.verdict}>
          <span className={s.label} style={{ color }}>
            {bias.label}
          </span>
          <span className={s.caption}>{bias.caption}</span>
        </p>
      </div>

      <dl className={s.rows}>
        <div className={s.row}>
          <dt>Max Pain Strike</dt>
          <dd>{maxPain.toFixed(2)}</dd>
        </div>
        <div className={s.row}>
          {/* Spot, not the futures price. The other Options Lab charts overlay
              futures because it is the tradable contract, but max pain is about
              where the underlying settles. */}
          <dt>Spot Price</dt>
          <dd>{spot.toFixed(2)}</dd>
        </div>
      </dl>

      <div className={s.insight}>
        <p className={s.insightTitle}>Market Insight</p>
        <p className={s.insightBody}>{bias.insight}</p>
      </div>
    </div>
  );
}
