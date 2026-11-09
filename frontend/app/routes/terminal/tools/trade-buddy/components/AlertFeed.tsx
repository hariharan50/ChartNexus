import { useQuery } from '@tanstack/react-query';
import { cx } from '$shared/ui/cx';
import {
  alertLook,
  describeAlert,
  describeChannels,
  formatPrice,
  formatTime,
  getAlerts,
  REFETCH_MS,
  type AlertsResponse,
  type Watchable
} from '../trade-buddy-data';
import s from './AlertFeed.module.css';

/**
 * What has actually gone out today.
 *
 * The live state forgets. A level touched at 09:40 and idle again by 10:00
 * leaves no trace in the state machine, so the only record of the morning used
 * to be the messages on your phone — which meant the page could tell you where
 * price is now but never what you had already missed.
 *
 * Newest first, because the question is almost always "what just happened" and
 * an ascending list makes that the thing you scroll to.
 *
 * Nothing here is derived from live data: each entry renders only the fields
 * stored with it. An old entry re-measured against the current price or the
 * current bands would be quietly wrong, and a log you cannot trust is worse
 * than no log.
 */
interface Props {
  symbol: Watchable;
}

export default function AlertFeed({ symbol }: Props) {
  const alerts = useQuery<AlertsResponse>({
    queryKey: ['trade-buddy', 'alerts', symbol],
    queryFn: () => getAlerts(symbol),
    refetchInterval: REFETCH_MS
  });

  // A backend older than this endpoint answers 404, and the query rejects.
  // That is a deploy skew, not a fault worth reporting to a trader: the empty
  // state says "nothing yet", which is the one thing that is still true.
  const items = alerts.data?.alerts ?? [];

  return (
    <section className={s.card} aria-labelledby="tb-feed">
      <header className={s.head}>
        <h2 id="tb-feed" className={s.title}>
          Today&apos;s alerts
        </h2>
        {items.length > 0 && <span className={s.count}>{items.length} sent</span>}
      </header>

      {items.length === 0 ? (
        <div className={s.empty}>
          <svg className={s.emptyIcon} viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M18 15.5V11a6 6 0 1 0-12 0v4.5L4.5 18h15L18 15.5Z"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinejoin="round"
            />
            <path
              d="M10 20.4a2.3 2.3 0 0 0 4 0"
              fill="none"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
          </svg>
          <p className={s.emptyTitle}>Quiet so far</p>
          <p className={s.emptyDetail}>
            Approaches, touches, breaks and reclaims show up here as they go out.
          </p>
        </div>
      ) : (
        <ol className={s.list}>
          {items.map((item, index) => {
            const look = alertLook(item.kind);
            return (
              <li key={`${item.at}-${item.label}-${index}`} className={s.item}>
                <div className={s.itemHead}>
                  <time className={s.time} dateTime={item.at}>
                    {formatTime(item.at).slice(0, 5)}
                  </time>
                  <span className={cx(s.kind, s[`tone_${look.tone}`])}>{look.label}</span>
                  <span className={s.level}>
                    {item.label} · {formatPrice(item.level_price)}
                  </span>
                </div>
                <p className={s.detail}>{describeAlert(item)}</p>
                <p className={cx(s.channels, item.channels.length === 0 && s.undelivered)}>
                  {describeChannels(item.channels)}
                </p>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
