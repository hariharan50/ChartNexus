import { fmtGex, fmtStrike, type GexReadoutRow } from '../gex-data';
import s from './GexReadout.module.css';

/**
 * The hovered strike's figures, beside the plot rather than over it.
 *
 * A floating tooltip on this chart covered the bars it was describing — and
 * worst around spot, where the strikes anyone is actually reading are. Pinned
 * here it costs a strip of width and nothing else, and the numbers hold still
 * long enough to be compared against the levels row underneath.
 *
 * It never goes blank: with the pointer off the chart it falls back to the
 * strike nearest spot, so the panel reads as part of the page rather than as an
 * empty box waiting to be hovered.
 */
interface Props {
  strike: number | null;
  rows: GexReadoutRow[];
  /** True when this is the fallback rather than something the reader pointed at. */
  isDefault: boolean;
}

export default function GexReadout({ strike, rows, isDefault }: Props) {
  return (
    <aside className={s.panel} aria-live="polite" aria-label="Hovered strike">
      {strike === null ? (
        <p className={s.empty}>No strikes in this window.</p>
      ) : (
        <>
          <p className={s.caption}>{isDefault ? 'Nearest spot' : 'Strike'}</p>
          <p className={s.strike}>{fmtStrike(strike)}</p>
          <dl className={s.rows}>
            {rows.map((row) => (
              <div key={row.label} className={s.row}>
                <dt className={s.label}>
                  <span className={s.swatch} style={{ background: row.color }} aria-hidden="true" />
                  {row.label}
                </dt>
                <dd className={s.value}>{fmtGex(row.value)}</dd>
              </div>
            ))}
          </dl>
          {rows.length === 0 ? <p className={s.empty}>Both series are hidden.</p> : null}
        </>
      )}
    </aside>
  );
}
