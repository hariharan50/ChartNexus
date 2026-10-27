import { useEffect, useState } from 'react';
import {
  type ExpiryRadar,
  alertable,
  expiryDateLabel,
  kindLabel
} from '$contexts/market-data/expiry-calendar';
import { cx } from '$shared/ui/cx';
import IconClose from '$shared/ui/icons/IconClose';
import { useNotificationPreferencesStore } from '$shared/ui/notification-preferences-store';
import ExpiryTriangle from './ExpiryTriangle';
import s from './ExpiryAlert.module.css';

interface Props {
  radars: readonly ExpiryRadar[];
  /** The session date, used to key the dismissal so it does not outlive the day. */
  sessionDate: string;
}

const DISMISS_KEY = 'cn-expiry-alert-dismissed';

/**
 * Whether this session has already dismissed today's banner.
 *
 * Keyed by date, in sessionStorage. Both halves of that matter: an undated key
 * would silence tomorrow's expiry because the reader closed today's, and
 * localStorage would carry the dismissal across days as well as tabs. A banner
 * that stays shut after the thing it warned about has changed is worse than
 * one that never appeared.
 */
function readDismissed(sessionDate: string): boolean {
  try {
    return window.sessionStorage.getItem(DISMISS_KEY) === sessionDate;
  } catch {
    // Private-mode storage can throw rather than return null. A banner that
    // cannot remember being dismissed is a far smaller fault than a crash.
    return false;
  }
}

/**
 * The expiry-day interruption.
 *
 * Fires only at `today` and `tomorrow`. Three days out it would be on screen
 * most of the week, and a banner that is always there stops being read — the
 * triangles on the cards already carry the slower horizon.
 *
 * Gated on `Settings → Notifications → Market schedule`, which until now had no
 * consumer anywhere in the app. Turning it off leaves the cards and their
 * triangles in place and only removes the interruption, which is what that
 * toggle should mean.
 *
 * It renders nothing on the server and on the first client render: the
 * dismissal lives in sessionStorage, and reading storage during render is what
 * makes the two disagree — the rule `use-hydrate-preferences` documents for the
 * preference stores.
 */
export default function ExpiryAlert({ radars, sessionDate }: Props) {
  const enabled = useNotificationPreferencesStore((state) => state.toggles.marketSchedule);
  const [dismissed, setDismissed] = useState<boolean | undefined>(undefined);

  useEffect(() => {
    setDismissed(readDismissed(sessionDate));
  }, [sessionDate]);

  const hits = alertable(radars);
  if (!enabled || dismissed !== false || hits.length === 0) return null;

  // The soonest hit sets the tone for the whole strip. One expiry today among
  // three tomorrows is still an expiry today.
  const lead = hits[0]!;
  const tone = lead.marker.urgency === 'today' ? 'today' : 'tomorrow';

  const dismiss = () => {
    setDismissed(true);
    try {
      window.sessionStorage.setItem(DISMISS_KEY, sessionDate);
    } catch {
      // Dismissal simply will not persist. The banner still closes.
    }
  };

  return (
    <div className={cx(s.banner, s[tone])} role="status">
      <span className={s.lead}>
        <ExpiryTriangle kind={lead.marker.kind} urgency={lead.marker.urgency} />
      </span>

      <div className={s.body}>
        <p className={s.headline}>{tone === 'today' ? 'Expiry today' : 'Expiry tomorrow'}</p>
        <ul className={s.list}>
          {hits.map(({ radar, marker }) => (
            <li key={`${radar.key}-${marker.date}`} className={s.item}>
              <strong className={s.name}>{radar.label}</strong>{' '}
              {kindLabel(marker.kind).toLowerCase()} expiry{' '}
              {marker.daysAway === 0 ? 'today' : 'tomorrow'} ·{' '}
              <span className="cn-numeric">{expiryDateLabel(marker.date)}</span>
            </li>
          ))}
        </ul>
      </div>

      <button type="button" className={s.close} onClick={dismiss} aria-label="Dismiss expiry alert">
        <IconClose />
      </button>
    </div>
  );
}
