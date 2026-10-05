import type { Pressure } from '$contexts/global-markets/types';
import { cx } from '$shared/ui/cx';
import { PRESSURE_LABELS, bandTone, fmtPercent, toNumber } from '../gia-data';
import s from './GapPressureGauge.module.css';

interface Props {
  pressure: Pressure;
}

/**
 * Global Gap Pressure, and every input that produced it.
 *
 * The composite weighs each market's overnight move by its pull on the Indian
 * gap and by how recently it closed — a market that shut forty minutes ago
 * tells you more about the next open than one that shut fourteen hours ago,
 * which is the thing a flat quote table cannot express.
 *
 * The waterfall is not decoration. A single score with no visible inputs is a
 * horoscope with a decimal point; showing which market contributed what is
 * what makes this checkable rather than something to be believed.
 */
export default function GapPressureGauge({ pressure }: Props) {
  const score = toNumber(pressure.score) ?? 0;
  const t = bandTone(pressure.band);

  // The gauge runs −100…+100, so zero sits at the midpoint.
  const needle = ((score + 100) / 200) * 100;
  const peak = Math.max(
    ...pressure.contributions.map((item) => Math.abs(toNumber(item.points) ?? 0)),
    1
  );

  return (
    <section className={s.wrap} aria-label="Global gap pressure">
      <header className={s.head}>
        <h2 className={s.title}>Global Gap Pressure</h2>
        <p className={s.sub}>Weighted by each market&apos;s pull and by how recently it closed</p>
      </header>

      <p className={cx(s.score, 'cn-numeric', t === 'up' && s.up, t === 'down' && s.down)}>
        {score > 0 ? '+' : score < 0 ? '−' : ''}
        {Math.abs(score).toFixed(1)}
      </p>
      <p className={cx(s.band, t === 'up' && s.up, t === 'down' && s.down)}>
        {PRESSURE_LABELS[pressure.band]}
      </p>

      <div className={s.gauge} role="img" aria-label={`Score ${score.toFixed(1)} of 100`}>
        <span className={s.zero} />
        <span
          className={cx(s.needle, t === 'up' && s.up, t === 'down' && s.down)}
          style={{ left: `${needle}%` }}
        />
      </div>
      <div className={s.scale} aria-hidden="true">
        <span>−100</span>
        <span>0</span>
        <span>+100</span>
      </div>

      <h3 className={s.breakdownTitle}>What made it</h3>
      <ul className={s.waterfall}>
        {pressure.contributions.map((item) => {
          const points = toNumber(item.points) ?? 0;
          const width = (Math.abs(points) / peak) * 50;
          return (
            <li className={s.row} key={item.key}>
              <span className={s.name}>{item.label}</span>
              <span className={s.track}>
                <span
                  className={cx(s.bar, points >= 0 ? s.up : s.down)}
                  style={
                    points >= 0
                      ? { left: '50%', width: `${width}%` }
                      : { right: '50%', width: `${width}%` }
                  }
                />
                <span className={s.mid} />
              </span>
              <span className={cx(s.move, 'cn-numeric')}>{fmtPercent(item.change_percent)}</span>
              <span
                className={cx(s.points, 'cn-numeric', points > 0 && s.up, points < 0 && s.down)}
              >
                {points > 0 ? '+' : points < 0 ? '−' : ''}
                {Math.abs(points).toFixed(1)}
              </span>
            </li>
          );
        })}
      </ul>

      {pressure.missing.length > 0 ? (
        <p className={s.missing}>
          No quote for {pressure.missing.join(', ')} — the score is built without{' '}
          {pressure.missing.length === 1 ? 'it' : 'them'}.
        </p>
      ) : null}

      <p className={s.caveat}>
        Weights are fixed, not fitted to realised gaps yet. Read the breakdown, not just the number.
      </p>
    </section>
  );
}
