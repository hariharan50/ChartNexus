import type { IndexHeader } from '$contexts/market-breadth/types';
import { cx } from '$shared/ui/cx';
import { basisLabel, coverageLabel, fmtPercent, fmtPrice, toNumber } from '../analysis-data';
import s from '../analysis.module.css';

/**
 * The index itself, above whatever the page draws about it.
 *
 * Four facts, and the last two are not decoration:
 *
 * * **Coverage** — "48 of 50 priced · 96.2% of index weight". A board missing
 *   two heavyweights and one missing two minnows have the same member count
 *   and very different worth, so both halves are shown.
 * * **Basis** — which market the prices came from. A front-month future tracks
 *   its underlying closely and diverges with carry and the roll; close enough
 *   to rank contributors, not the cash print, so the page names it instead of
 *   letting a reader assume.
 */
export default function IndexStrip({ header }: { header: IndexHeader | undefined }) {
  if (!header) return null;

  const change = toNumber(header.change_absolute);
  const percent = toNumber(header.change_percent);
  const tone = change === null || change === 0 ? undefined : change > 0 ? s.up : s.down;

  return (
    <div className={s.tiles}>
      <div className={s.tile}>
        <span className={s.tileLabel}>Index level</span>
        <span className={s.tileValue}>{fmtPrice(header.level)}</span>
        <span className={s.tileHint}>Prev close {fmtPrice(header.previous_close)}</span>
      </div>
      <div className={s.tile}>
        <span className={s.tileLabel}>Change</span>
        <span className={cx(s.tileValue, tone)}>
          {change === null
            ? '—'
            : `${change > 0 ? '+' : change < 0 ? '−' : ''}${Math.abs(change).toFixed(2)}`}
        </span>
        <span className={cx(s.tileHint, tone)}>{fmtPercent(percent)}</span>
      </div>
      <div className={s.tile}>
        <span className={s.tileLabel}>Coverage</span>
        <span className={s.tileValue}>
          {header.covered}/{header.universe}
        </span>
        <span className={s.tileHint}>{coverageLabel(header)}</span>
      </div>
      <div className={s.tile}>
        <span className={s.tileLabel}>Price basis</span>
        <span className={s.tileValue}>{basisLabel(header)}</span>
        <span className={s.tileHint}>
          {header.basis === 'futures' ? 'Tracks cash; diverges with the basis' : 'Equity prints'}
        </span>
      </div>
    </div>
  );
}
