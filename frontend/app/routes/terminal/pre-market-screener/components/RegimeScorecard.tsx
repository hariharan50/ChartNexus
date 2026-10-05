import type { Regime } from '$contexts/pre-market/types';
import { cx } from '$shared/ui/cx';
import { CONFIDENCE_NOTES, REGIME_LABELS, fmtOne, regimeTone, stanceTone } from '../pms-data';
import s from './RegimeScorecard.module.css';

interface Props {
  regime: Regime;
}

/** 0-100 mapped onto the meter's width. */
function position(score: number): string {
  return `${Math.max(0, Math.min(100, score))}%`;
}

/**
 * Six axes, a composite, and every input that produced it.
 *
 * Modelled on GIA's `GapPressureGauge`, and for the same reason: this does not
 * emit BUY or SELL, it emits a reading the user can take apart. Every factor
 * row carries the raw number it was read from, because a composite whose
 * inputs cannot be inspected is a horoscope with a decimal point — if the
 * score says 68 and you cannot see it got there on a strong EMA stack and weak
 * breadth, you cannot disagree with it, and a number you cannot disagree with
 * is worth nothing.
 *
 * The coverage line is load-bearing too. A score built from three of nine
 * inputs is a different claim from one built on all nine, and rendering them
 * identically is the quiet way a screener lies.
 */
export default function RegimeScorecard({ regime }: Props) {
  const tone = regimeTone(regime.band);

  return (
    <div className={s.wrap}>
      <div className={s.head}>
        <p className={cx(s.band, s[tone ?? 'flat'])}>{REGIME_LABELS[regime.band]}</p>
        <p className={cx(s.score, 'cn-numeric', s[tone ?? 'flat'])}>{fmtOne(regime.score)}</p>
      </div>

      <div className={s.meter} aria-hidden="true">
        <span className={s.track} />
        <span
          className={cx(s.needle, s[tone ?? 'flat'])}
          style={{ left: position(regime.score) }}
        />
      </div>

      <p className={s.coverage}>
        Built on <strong>{regime.inputs_present}</strong> of {regime.inputs_total} inputs ·{' '}
        {CONFIDENCE_NOTES[regime.confidence]}
      </p>

      <ul className={s.axes}>
        {regime.axes.map((axis) => (
          <li key={axis.axis} className={cx(s.axis, !axis.resolved && s.muted)}>
            <span className={s.axisLabel}>{axis.label}</span>
            <span className={cx(s.axisPoints, 'cn-numeric', s[stanceTone(axis.stance) ?? 'flat'])}>
              {axis.resolved ? fmtOne(axis.points) : '—'}
            </span>
          </li>
        ))}
      </ul>

      <table className={s.factors}>
        <caption className={s.caption}>
          Every factor, with the figure it was read from. Weights are judgement, not a fit.
        </caption>
        <thead>
          <tr>
            <th scope="col">Factor</th>
            <th scope="col">Reading</th>
            <th scope="col" className={s.right}>
              Points
            </th>
          </tr>
        </thead>
        <tbody>
          {regime.factors.map((factor) => (
            <tr key={factor.key}>
              <th scope="row">
                {factor.label}
                {factor.note ? <span className={s.factorNote}>{factor.note}</span> : null}
              </th>
              <td className="cn-numeric">{factor.reading}</td>
              <td className={cx(s.right, 'cn-numeric', s[stanceTone(factor.stance) ?? 'flat'])}>
                {fmtOne(factor.points)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <p className={s.caveat}>
        A multi-axis read, not a trade signal. The weights are fixed and unfitted, and the market
        routinely opens against readings like this one.
      </p>
    </div>
  );
}
