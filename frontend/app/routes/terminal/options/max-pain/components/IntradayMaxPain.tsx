import { useMemo } from 'react';
import { cx } from '$shared/ui/cx';
import IconChart from '$shared/ui/icons/IconChart';
import SeriesChart from '../../components/SeriesChart';
// The same index-level formatter the PCR chart's price axis uses, so two
// Options Lab charts never round the same level differently.
import { fmtPrice } from '../../pcr/pcr-data';
import { convergence, type MaxPainSeriesView } from '../max-pain-data';
import s from './IntradayMaxPain.module.css';

interface Props {
  view: MaxPainSeriesView | undefined;
  loading: boolean;
  /** Historical mode says "no session archived", live says "not yet". */
  historical: boolean;
}

/**
 * The max-pain level through the session, against the tradable future.
 *
 * The bar chart below this one answers "where is max pain now". This answers
 * "where has it been going", which is a different and usually more useful
 * question: max pain migrates as writers reposition, and a level that keeps
 * stepping toward spot is a market being pinned, while one that runs away from
 * it is writers giving ground. A single snapshot cannot tell those apart.
 *
 * **One shared price scale.** Max pain is an index level, same unit as the
 * future, and the whole reading here is the *distance* between the two lines.
 * On separate axes they could appear to cross when they never did.
 */
export default function IntradayMaxPain({ view, loading, historical }: Props) {
  const reading = useMemo(() => convergence(view), [view]);

  const lines = useMemo(
    () => [
      {
        id: 'max-pain',
        label: 'Max Pain',
        color: MAX_PAIN_COLOR,
        values: view?.max_pain ?? [],
        // A strike, not a price: it sits at 23,400 and then at 23,350, and was
        // never at 23,380 on the way.
        step: true
      }
    ],
    [view]
  );

  if (loading && !view) {
    return <div className={cx(s.panel, s.muted)}>Loading Intraday Max Pain…</div>;
  }

  if (!view || view.data_quality === 'empty' || view.t.length === 0) {
    return (
      <section className={s.panel}>
        <h2 className={s.title}>
          <span className={s.ico} aria-hidden="true">
            <IconChart />
          </span>{' '}
          Intraday Max Pain
        </h2>
        <p className={s.empty}>
          {historical
            ? 'No session archived for that date.'
            : 'No captures yet today — the series starts once the session is being archived.'}
        </p>
      </section>
    );
  }

  return (
    <div className={s.wrap}>
      <SeriesChart
        title="Intraday Max Pain"
        subtitle="Where the pin has moved through the session, against the tradable future."
        icon={<IconChart />}
        valueAxisName="Level"
        lines={lines}
        timestamps={view.t}
        futures={view.fut}
        formatValue={fmtPrice}
        formatPrice={fmtPrice}
        group="max-pain"
        sharedPriceAxis
        zoomable
      />

      {reading ? (
        <div className={s.reading}>
          <div className={s.cell}>
            <p className={s.label}>Distance to pin</p>
            <p
              className={cx(
                s.value,
                'cn-numeric',
                reading.distance > 0 && s.up,
                reading.distance < 0 && s.down
              )}
            >
              {signed(reading.distance)} ({signed(reading.distancePct, 2)}%)
            </p>
            <p className={s.note}>
              {reading.distance > 0 ? 'Price above max pain' : 'Price below max pain'}
            </p>
          </div>

          <div className={s.cell}>
            <p className={s.label}>Pin moved today</p>
            <p
              className={cx(
                s.value,
                'cn-numeric',
                reading.shift > 0 && s.up,
                reading.shift < 0 && s.down
              )}
            >
              {reading.drift === 'unchanged' ? 'Unchanged' : signed(reading.shift)}
            </p>
            <p className={s.note}>
              {reading.drift === 'unchanged'
                ? `Pinned at ${fmtPrice(reading.maxPain)} all session`
                : `From ${fmtPrice(reading.openMaxPain)} to ${fmtPrice(reading.maxPain)}`}
            </p>
          </div>

          <div className={s.cell}>
            <p className={s.label}>Since the open</p>
            <p className={cx(s.value, s[reading.approach])}>{APPROACH_LABELS[reading.approach]}</p>
            <p className={s.note}>{APPROACH_NOTES[reading.approach]}</p>
          </div>
        </div>
      ) : null}

      <p className={s.caption}>
        Max pain is the level where the most option value would expire worthless, so writers are
        drawn to defend it into expiry.
        {view.data_quality === 'live_proxy'
          ? ' Only the open and now are available — today’s session has not been archived, so the line between them is two points, not a path.'
          : view.open_is_estimated
            ? ' The 09:15 point is reconstructed from each leg’s day change, because the archive starts later than the bell.'
            : ''}
      </p>
    </div>
  );
}

/** The amber the max-pain marker already uses on the profile chart. */
const MAX_PAIN_COLOR = '#f59e0b';

const APPROACH_LABELS: Record<string, string> = {
  converging: 'Converging',
  diverging: 'Diverging',
  steady: 'Holding'
};

const APPROACH_NOTES: Record<string, string> = {
  converging: 'The gap has narrowed since the open',
  diverging: 'The gap has widened since the open',
  steady: 'The gap is about where it opened'
};

/** Signed, with a true minus — the direction is the reading. */
function signed(value: number, digits = 0): string {
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}${Math.abs(value).toLocaleString('en-IN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  })}`;
}
