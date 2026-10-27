import {
  type ExpiryMarker,
  type ExpiryRadar,
  countdownLabel,
  expiryDateLabel,
  kindLabel
} from '$contexts/market-data/expiry-calendar';
import { cx } from '$shared/ui/cx';
import ExpiryTriangle from './ExpiryTriangle';
import s from './ExpiryCard.module.css';

interface Props {
  radar: ExpiryRadar;
  /** The listed-expiry query is still in flight. */
  loading?: boolean;
}

/** `NIFTY 50 weekly expiry tomorrow, Tue 28 Oct` — the card's read, in words. */
function spoken(label: string, marker: ExpiryMarker): string {
  const when =
    marker.daysAway === 0
      ? 'today'
      : marker.daysAway === 1
        ? 'tomorrow'
        : `in ${marker.daysAway} days`;
  return `${label} ${kindLabel(marker.kind).toLowerCase()} expiry ${when}, ${expiryDateLabel(marker.date)}`;
}

/**
 * One index's settlement calendar.
 *
 * Each row is a triangle, the contract it names, the date, and how far off it
 * is. The triangle is decoration — it is `aria-hidden`, and every row carries
 * the same information as text, so the card does not depend on telling red
 * from amber.
 *
 * Two states are stated rather than implied, for the same reason
 * `GapIndicatorCard` states its provenance:
 *
 * * **No weekly series.** BANK NIFTY's weeklies were withdrawn, so the card
 *   says so. A card with one row and no explanation looks like half a card
 *   that failed to load.
 * * **A scheduled date.** When the broker's calendar has not arrived (or is
 *   the mock's), the date comes from the published settlement rule and is
 *   labelled — holidays move expiries, and a computed date presented as a
 *   confirmed one is the failure this whole module is arranged to avoid.
 */
export default function ExpiryCard({ radar, loading = false }: Props) {
  if (loading && radar.rows.length === 0) {
    return (
      <div className={s.card}>
        <span className={s.label}>{radar.label}</span>
        <div className={s.skeleton} aria-hidden="true">
          <span className={s.skelRow} />
          <span className={s.skelRow} />
        </div>
      </div>
    );
  }

  return (
    <div className={s.card}>
      <span className={s.label}>{radar.label}</span>

      <ul className={s.rows}>
        {radar.rows.map((marker) => (
          <li
            key={`${marker.kind}-${marker.date}`}
            className={cx(s.row, s[marker.urgency])}
            aria-label={spoken(radar.label, marker)}
          >
            <span className={s.glyph}>
              <ExpiryTriangle kind={marker.kind} urgency={marker.urgency} />
            </span>
            <span className={s.kind}>{kindLabel(marker.kind)}</span>
            <span className={cx(s.date, 'cn-numeric')}>{expiryDateLabel(marker.date)}</span>
            <span className={cx(s.countdown, s[`c_${marker.urgency}`])}>
              {countdownLabel(marker.daysAway)}
            </span>
          </li>
        ))}
      </ul>

      <div className={s.notes}>
        {radar.weeklyRetired ? (
          <p className={s.note}>No weekly series — this index settles monthly.</p>
        ) : null}
        {radar.estimated ? (
          <p className={cx(s.note, s.noteWarn)}>
            Scheduled date — awaiting the broker&apos;s calendar, so a holiday could still move it.
          </p>
        ) : null}
      </div>
    </div>
  );
}
