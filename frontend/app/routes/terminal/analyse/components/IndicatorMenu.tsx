import { cx } from '$shared/ui/cx';
import {
  INDICATOR_CATEGORIES,
  INDICATORS,
  type IndicatorId,
  type IndicatorEntry
} from '../indicators';
import s from './IndicatorMenu.module.css';

/**
 * The Indicators panel: what is already on the chart, then the catalogue to add
 * from, grouped by what each indicator measures.
 *
 * The two halves answer different questions and so are not one list. "What am I
 * looking at, and how do I get rid of it" is the question a reader asks with a
 * chart already covered in lines, and answering it by hunting for the ticked
 * rows scattered through a catalogue gets worse with every indicator added. The
 * applied section puts them together, in the order they were added, each with
 * its own remove action.
 *
 * Below that the catalogue is grouped — trend, volatility, volume, momentum —
 * because someone reaching for a band is not helped by reading past every
 * oscillator to find it.
 */
interface Props {
  /** Applied indicator ids, in the order the reader added them. */
  active: IndicatorId[];
  /** Adds when absent, removes when present — one action for both directions. */
  onToggle: (id: IndicatorId) => void;
}

export default function IndicatorMenu({ active, onToggle }: Props) {
  // Ordered by when it was added, not by catalogue order: the list should read
  // the way the chart was built up.
  const applied = active
    .map((id) => INDICATORS.find((entry) => entry.id === id))
    .filter((entry): entry is IndicatorEntry => entry !== undefined);

  return (
    <div className={s.panel}>
      {applied.length > 0 ? (
        <section className={s.section} role="group" aria-label="On this chart">
          <p className={s.sectionLabel}>On this chart</p>
          {applied.map((entry) => (
            <div key={entry.id} className={s.appliedRow}>
              <span className={s.swatch} style={{ background: entry.color }} aria-hidden="true" />
              <span className={s.name}>{entry.label}</span>
              <button
                type="button"
                className={s.action}
                // Named for what it removes: a row of identical "remove" buttons
                // is unusable to anyone hearing them read out one at a time.
                aria-label={`Remove ${entry.label}`}
                onClick={() => onToggle(entry.id)}
              >
                remove
              </button>
            </div>
          ))}
        </section>
      ) : null}

      {INDICATOR_CATEGORIES.map((category) => {
        const entries = INDICATORS.filter((entry) => entry.category === category.id);
        if (entries.length === 0) return null;

        return (
          <section key={category.id} className={s.section} role="group" aria-label={category.label}>
            <p className={s.sectionLabel}>{category.label}</p>
            {entries.map((entry) => {
              const on = active.includes(entry.id);
              return (
                <button
                  key={entry.id}
                  type="button"
                  role="menuitemcheckbox"
                  aria-checked={on}
                  className={cx(s.item, on && s.itemOn)}
                  onClick={() => onToggle(entry.id)}
                >
                  <span
                    className={s.swatch}
                    style={{ background: entry.color }}
                    aria-hidden="true"
                  />
                  <span className={s.name}>{entry.label}</span>
                  {/* Every indicator here is already in the applied section when
                      it is on; this is the confirmation at the point of the
                      click, so the row the pointer is on tells the truth too. */}
                  <span className={s.check} aria-hidden="true">
                    {on ? '✓' : ''}
                  </span>
                </button>
              );
            })}
          </section>
        );
      })}
    </div>
  );
}
