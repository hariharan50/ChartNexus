import { cx } from '$shared/ui/cx';
import { formatPrice, stateLook, type Watchable, type WatchRow } from '../trade-buddy-data';
import s from './WatchlistStrip.module.css';

/**
 * All three indices at once, so one glance answers "is anything happening".
 *
 * The page below shows one instrument in full. Without this you would have to
 * cycle the picker to find out that BANKNIFTY had broken a level while you
 * were reading NIFTY — which is exactly the thing the alerts exist to stop you
 * having to do, and it would be odd for the page to reintroduce it.
 *
 * Unmarked indices are listed rather than omitted. An index you forgot to mark
 * produces no alerts all day, and absence is the one state that looks
 * identical to "nothing happened".
 */
interface Props {
  rows: readonly WatchRow[];
  selected: Watchable;
  onSelect: (symbol: Watchable) => void;
}

export default function WatchlistStrip({ rows, selected, onSelect }: Props) {
  if (rows.length === 0) return null;

  return (
    <div className={s.strip} role="tablist" aria-label="Watched instruments">
      {rows.map((row) => {
        const look = row.attention ? stateLook(row.attention) : null;
        const active = row.symbol === selected;
        return (
          <button
            key={row.symbol}
            type="button"
            role="tab"
            aria-selected={active}
            className={cx(s.card, active && s.active, !row.watched && s.idle)}
            onClick={() => onSelect(row.symbol)}
          >
            <span className={s.head}>
              <span className={s.symbol}>{row.symbol}</span>
              {/* Word + glyph, never colour alone. */}
              {look ? (
                <span className={cx(s.badge, s[`tone_${look.tone}`])}>
                  <span aria-hidden="true">{look.glyph}</span> {look.label}
                </span>
              ) : (
                <span className={s.badgeQuiet}>{row.watched ? 'Quiet' : 'No levels'}</span>
              )}
            </span>

            <span className={s.price}>
              {row.last_price !== null ? formatPrice(row.last_price) : '—'}
            </span>

            <span className={s.meta}>
              {row.watched ? (
                <>
                  {row.nearest_label ? (
                    <>
                      {row.nearest_label} {formatDistance(row.nearest_distance)}
                    </>
                  ) : (
                    `${row.levels_marked} level${row.levels_marked === 1 ? '' : 's'}`
                  )}
                  {/* A degraded band set is worth seeing here, not only in the
                      settings panel: it silently changes what every alert on
                      this instrument means. */}
                  {row.levels_stale ? (
                    <span className={s.stale} title="Levels are from an earlier session">
                      {' '}
                      · stale
                    </span>
                  ) : (
                    row.band_source === 'points' && (
                      <span className={s.unscaled} title="ATR unavailable — bands are unscaled">
                        {' '}
                        · unscaled
                      </span>
                    )
                  )}
                </>
              ) : (
                'Not watched'
              )}
            </span>
          </button>
        );
      })}
    </div>
  );
}

function formatDistance(distance: number | null): string {
  if (distance === null) return '';
  return `${distance.toFixed(0)} pts away`;
}
