import { cx } from '$shared/ui/cx';
import type { Candle } from '$shared/charts/tv/LwChart';
import { fmtPrice } from '../analyse-data';
import s from './ChartLegend.module.css';

/**
 * The OHLC readout over the chart's top-left corner.
 *
 * Reads the bar under the crosshair, falling back to the newest one when the
 * pointer is off the plot — which is the state it spends most of its life in,
 * and where "the last close" is the number anyone wants.
 *
 * Absolutely positioned over the canvas rather than sitting above it: the
 * reference puts it there, and a legend in the page flow costs the chart the
 * height it occupies on every screen.
 */
interface Props {
  symbol: string;
  badge: string;
  bar: Candle | null;
  volume: number | null;
}

export default function ChartLegend({ symbol, badge, bar, volume }: Props) {
  if (!bar) return null;
  const change = bar.close - bar.open;
  const pct = bar.open === 0 ? 0 : (change / bar.open) * 100;
  const up = change >= 0;

  return (
    <div className={s.legend}>
      <div className={s.row}>
        <span className={s.badge}>{badge}</span>
        <span className={s.symbol}>{symbol}</span>
        <span className={s.ohlc}>
          <span className={s.key}>O</span>
          <span className={cx(s.val, up ? s.up : s.down)}>{fmtPrice(bar.open)}</span>
          <span className={s.key}>H</span>
          <span className={cx(s.val, up ? s.up : s.down)}>{fmtPrice(bar.high)}</span>
          <span className={s.key}>L</span>
          <span className={cx(s.val, up ? s.up : s.down)}>{fmtPrice(bar.low)}</span>
          <span className={s.key}>C</span>
          <span className={cx(s.val, up ? s.up : s.down)}>{fmtPrice(bar.close)}</span>
          <span className={cx(s.val, up ? s.up : s.down)}>
            {up ? '+' : ''}
            {fmtPrice(change)} ({up ? '+' : ''}
            {pct.toFixed(2)}%)
          </span>
        </span>
      </div>
      {volume !== null ? (
        <div className={s.row}>
          <span className={s.key}>Volume</span>
          <span className={s.vol}>{volume.toLocaleString('en-IN')}</span>
        </div>
      ) : null}
    </div>
  );
}
