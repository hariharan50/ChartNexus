import { useMemo, useState } from 'react';
import LwChart, { type Candle, type HistogramSpec } from '$shared/charts/tv/LwChart';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { cx } from '$shared/ui/cx';
import {
  CALL_COLOR,
  PUT_COLOR,
  fmtOi,
  fmtPrice,
  toCandles,
  toFlowBars,
  toVolumeBars,
  type SmartOiBar
} from '../smart-oi-data';
import s from './PricePanel.module.css';

/**
 * The left column: price, OI flow and option volume on one time axis.
 *
 * Three panes rather than three charts, because the whole reading is vertical —
 * "the tape broke out on the bar that puts were written into" is only visible
 * if the bar is in the same column in all three. Separate charts would each own
 * their own time scale and drift apart the moment one of them had a gap.
 *
 * The legend is hover-driven off the price pane's crosshair. When the pointer
 * leaves, it falls back to the newest bar rather than blanking — an empty
 * legend on a live chart reads as a data failure.
 */
interface Props {
  bars: SmartOiBar[];
  smartOi: (number | null)[];
  callVol: (number | null)[];
  putVol: (number | null)[];
  symbol: string;
  /** Identity of the drawn dataset; a change re-fits the view, a poll does not. */
  resetKey: string;
  empty?: string | undefined;
}

/** Pane 0 is price. */
const SMART_OI_PANE = 1;
const VOLUME_PANE = 2;
/* Each sub-pane's share of the chart. The two of them take a bit under half,
   which is what the reference gives them — the flow and the volume are the
   subject here, not a footnote under the price. */
const SUB_PANE_FRACTION = 0.22;

export default function PricePanel({
  bars,
  smartOi,
  callVol,
  putVol,
  symbol,
  resetKey,
  empty
}: Props) {
  const theme = useChartTheme();
  const [hover, setHover] = useState<Candle | null>(null);
  const [showFlow, setShowFlow] = useState(true);
  const [showVolume, setShowVolume] = useState(true);

  const candles = useMemo(() => toCandles(bars), [bars]);

  const histograms = useMemo<HistogramSpec[]>(() => {
    const specs: HistogramSpec[] = [];
    if (showFlow) {
      specs.push({
        id: 'smart-oi',
        paneIndex: SMART_OI_PANE,
        paneFraction: SUB_PANE_FRACTION,
        format: axisOi,
        // Green where puts were written into the bar, red where calls were.
        data: toFlowBars(bars, smartOi, { up: CALL_COLOR, down: PUT_COLOR })
      });
    }
    if (showVolume) {
      // Both sides share one pane, the way the reference draws them: the
      // comparison between them is the point, and two bands would put a
      // gridline between the two numbers a reader is subtracting.
      specs.push({
        id: 'call-vol',
        paneIndex: VOLUME_PANE,
        paneFraction: SUB_PANE_FRACTION,
        format: axisOi,
        data: toVolumeBars(bars, callVol, CALL_COLOR)
      });
      specs.push({
        id: 'put-vol',
        paneIndex: VOLUME_PANE,
        paneFraction: SUB_PANE_FRACTION,
        format: axisOi,
        data: toVolumeBars(bars, putVol, PUT_COLOR)
      });
    }
    return specs;
  }, [bars, smartOi, callVol, putVol, showFlow, showVolume]);

  // The bar the legend describes: whatever the crosshair is on, else the newest.
  const at = useMemo(() => {
    if (hover === null) return bars.length - 1;
    const found = candles.findIndex((candle) => candle.time === hover.time);
    return found === -1 ? bars.length - 1 : found;
  }, [hover, candles, bars.length]);

  const bar = bars[at];

  return (
    <section className={s.panel}>
      <div className={s.legend}>
        <span className={cx(s.entry, s.symbol)}>{symbol}</span>
        <button
          type="button"
          className={cx(s.entry, !showFlow && s.off)}
          onClick={() => setShowFlow((on) => !on)}
          aria-pressed={showFlow}
        >
          <span className={s.swatch} style={{ background: theme.accent }} />
          Smart OI
        </button>
        <button
          type="button"
          className={cx(s.entry, !showVolume && s.off)}
          onClick={() => setShowVolume((on) => !on)}
          aria-pressed={showVolume}
        >
          <span className={s.swatch} style={{ background: CALL_COLOR }} />
          Volume
        </button>

        {bar ? (
          <span className={s.readout}>
            <span className={s.pair}>
              O <b>{fmtPrice(bar.o)}</b>
            </span>
            <span className={s.pair}>
              H <b>{fmtPrice(bar.h)}</b>
            </span>
            <span className={s.pair}>
              L <b>{fmtPrice(bar.l)}</b>
            </span>
            <span className={s.pair}>
              C <b className={bar.c >= bar.o ? s.pos : s.neg}>{fmtPrice(bar.c)}</b>
            </span>
            <span className={s.sep} aria-hidden="true">
              ·
            </span>
            <span className={s.pair}>
              Smart OI <b>{signed(smartOi[at])}</b>
            </span>
            <span className={s.pair}>
              Call Vol <b style={{ color: CALL_COLOR }}>{plain(callVol[at])}</b>
            </span>
            <span className={s.pair}>
              Put Vol <b style={{ color: PUT_COLOR }}>{plain(putVol[at])}</b>
            </span>
          </span>
        ) : null}
      </div>

      {bars.length === 0 ? (
        <p className={s.empty}>{empty ?? 'No price history for this session yet.'}</p>
      ) : (
        <LwChart
          candles={candles}
          histograms={histograms}
          theme={theme}
          onHoverBar={setHover}
          resetKey={resetKey}
          className={s.chart}
        />
      )}
    </section>
  );
}

/**
 * A sub-pane axis label: `1.24Cr`, and signed so a negative flow reads as one.
 *
 * `fmtOi` is the same formatter the legend and every other Options Lab page
 * use, but it is unsigned — right for a total, wrong for an axis that crosses
 * zero, where `-2Cr` and `2Cr` would print identically.
 */
function axisOi(value: number): string {
  return `${value < 0 ? '−' : ''}${fmtOi(Math.abs(value))}`;
}

/** `null` prints as an em dash — the bar had no capture, which is not zero. */
function signed(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return `${value >= 0 ? '+' : '−'}${fmtOi(Math.abs(value))}`;
}

function plain(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  return fmtOi(value);
}
