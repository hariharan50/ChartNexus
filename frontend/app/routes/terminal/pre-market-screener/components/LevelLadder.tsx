import { Fragment } from 'react';
import type { Levels } from '$contexts/pre-market/types';
import { cx } from '$shared/ui/cx';
import { ORIGIN_LABELS, fmtAtr, fmtChange, fmtLevel, fmtPercent } from '../pms-data';
import s from './LevelLadder.module.css';

interface Props {
  levels: Levels;
}

/**
 * Every reference price in one ladder, with spot's place among them.
 *
 * Pivots, prior-day extremes, period ranges and the option book's heavy
 * strikes are merged rather than tabled separately, because that is how they
 * are traded — as one map. Each row names the method that produced it, which
 * is what makes the confluence list meaningful: two pivots agreeing is
 * arithmetic, a pivot agreeing with an option wall is two different sets of
 * participants arriving at the same price.
 *
 * Distance is given in ATR as well as points and percent, because forty points
 * means nothing until you know whether the index travels eighty a day or four
 * hundred — and this page covers three instruments of very different sizes.
 */
export default function LevelLadder({ levels }: Props) {
  return (
    <div className={s.wrap}>
      {levels.clusters.length ? (
        <div className={s.clusters}>
          <p className={s.clustersHead}>Where independent methods agree</p>
          <ul className={s.clusterList}>
            {levels.clusters.map((cluster) => (
              <li key={cluster.price} className={s.cluster}>
                <span className={cx(s.clusterPrice, 'cn-numeric')}>{fmtLevel(cluster.price)}</span>
                <span className={s.clusterOrigins}>
                  {cluster.origins.map((origin) => ORIGIN_LABELS[origin]).join(' · ')}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      <table className={s.table}>
        <caption className={s.caption}>
          Ordered high to low. Option-OI rows show where positioning sits, not levels that will
          hold.
        </caption>
        <thead>
          <tr>
            <th scope="col">Level</th>
            <th scope="col">From</th>
            <th scope="col" className={s.right}>
              Price
            </th>
            <th scope="col" className={s.right}>
              Distance
            </th>
            <th scope="col" className={s.right}>
              ATR
            </th>
          </tr>
        </thead>
        <tbody>
          {levels.ladder.map((level, index) => {
            const previous = levels.ladder[index - 1];
            // The spot marker slots between the first row above it and the
            // first below, so the ladder reads as a price axis rather than a
            // list that happens to be sorted.
            const crossesSpot =
              level.side === 'below' && (previous === undefined || previous.side !== 'below');

            return (
              <Fragment key={`${level.origin}-${level.label}`}>
                {crossesSpot ? (
                  <tr className={s.spotRow}>
                    <th scope="row" colSpan={2}>
                      Spot
                    </th>
                    <td className={cx(s.right, 'cn-numeric')}>{fmtLevel(levels.spot)}</td>
                    <td className={s.right} colSpan={2} />
                  </tr>
                ) : null}
                <tr>
                  <th scope="row">{level.label}</th>
                  <td className={s.origin}>{ORIGIN_LABELS[level.origin]}</td>
                  <td className={cx(s.right, 'cn-numeric')}>{fmtLevel(level.price)}</td>
                  <td className={cx(s.right, 'cn-numeric', s[level.side])}>
                    {fmtChange(level.distance_points)}
                    <span className={s.sub}>{fmtPercent(level.distance_percent)}</span>
                  </td>
                  <td className={cx(s.right, 'cn-numeric', s.sub)}>{fmtAtr(level.distance_atr)}</td>
                </tr>
              </Fragment>
            );
          })}
          {/* Price below every level is itself the reading — a breakdown — so
              the marker still renders rather than being dropped. */}
          {levels.ladder.every((level) => level.side === 'above') ? (
            <tr className={s.spotRow}>
              <th scope="row" colSpan={2}>
                Spot
              </th>
              <td className={cx(s.right, 'cn-numeric')}>{fmtLevel(levels.spot)}</td>
              <td className={s.right} colSpan={2} />
            </tr>
          ) : null}
        </tbody>
      </table>
    </div>
  );
}
