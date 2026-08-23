import { Link } from 'react-router';
import {
  useHuginAvailabilityQuery,
  useHuginEnrollmentQuery,
  useSetHuginEnrollmentMutation
} from '$contexts/hugin/queries';
import { cx } from '$shared/ui/cx';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'HUGIN Automation · MarketCompass' }];

export default function SettingsHugin() {
  const enrollment = useHuginEnrollmentQuery();
  const availability = useHuginAvailabilityQuery();
  const toggle = useSetHuginEnrollmentMutation();

  const enabled = enrollment.data?.enabled ?? false;
  const hasKey = availability.data?.available ?? false;
  const loading = enrollment.isLoading;
  const busy = toggle.isPending;

  return (
    <section className={s.panel}>
      <header className={s.head}>
        <h2 className={s.title}>HUGIN Automation</h2>
        <p className={s.sub}>
          HUGIN is an autonomous agent that wakes every hour during market hours, reads the market,
          grades its previous read, and builds a durable memory you can review on the{' '}
          <Link to="/ai-console/hugin">HUGIN tab</Link>.
        </p>
      </header>

      <div className={s.callout}>
        <strong>It runs on your own AI tokens.</strong> While on, HUGIN makes an LLM call every hour
        per instrument — whether or not you&apos;re looking. It is <strong>off by default</strong>;
        turn it on only if you want the hourly memory.
      </div>

      <div className={s.row}>
        <div className={s.rowText}>
          <span className={s.rowLabel}>Hourly market memory</span>
          <span className={cx(s.state, enabled ? s.stateOn : s.stateOff)}>
            {loading ? 'Loading…' : enabled ? 'On — running hourly' : 'Off'}
          </span>
        </div>

        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          aria-label="Toggle HUGIN automation"
          className={cx(s.switch, enabled && s.switchOn)}
          disabled={loading || busy}
          onClick={() => toggle.mutate(!enabled)}
        >
          <span className={s.knob} />
        </button>
      </div>

      {!hasKey ? (
        <p className={s.warn}>
          You have no LLM key configured, so HUGIN can&apos;t run yet even when on. Add one in{' '}
          <Link to="/settings/ai">AI Settings</Link> first.
        </p>
      ) : null}

      {toggle.isError ? (
        <p className={s.error}>Couldn&apos;t save that just now — try again.</p>
      ) : null}
    </section>
  );
}
