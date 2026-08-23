import type { CSSProperties, ReactNode } from 'react';
import { Link } from 'react-router';
import { useHuginEnrollmentQuery, useSetHuginEnrollmentMutation } from '$contexts/hugin/queries';
import {
  useMme100AvailabilityQuery,
  useMme100EnrollmentQuery,
  useSetMme100EnrollmentMutation
} from '$contexts/mme100/queries';
import { cx } from '$shared/ui/cx';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Power AI Agents · MarketCompass' }];

/**
 * One settings page for the autonomous, token-heavy agents. HUGIN and MME100 both
 * run on their own schedule in the background — they spend the owner's LLM tokens
 * whether or not anyone is looking — so they share this "power agent" home and its
 * cost framing, rather than a tab each. On-demand chat (HELLA/STRYX and the MME100
 * chat) has no automation and stays out of here.
 */
export default function SettingsPowerAgents() {
  // Both agents run on the one LLM key, so a single availability check drives the
  // shared "no key" warning; each card owns its own enrollment.
  const availability = useMme100AvailabilityQuery();
  const hasKey = availability.data?.available ?? false;

  return (
    <div className={s.wrap}>
      <header className={s.head}>
        <h1 className={s.title}>Power AI Agents</h1>
        <p className={s.sub}>
          These agents work on their own in the background — they read the market and call your LLM
          on a schedule, not just when you ask. Because they use noticeably more tokens than the
          on-demand chat, each is <strong>off by default</strong>; switch on only the automation you
          want.
        </p>
      </header>

      <div className={s.callout}>
        <strong>They run on your own AI tokens.</strong> While on, each makes LLM calls (and, for
        MME100, web searches) on its schedule, per instrument, whether or not you&apos;re looking.
      </div>

      {!hasKey ? (
        <p className={s.keyWarn}>
          You have no LLM key configured, so these agents can&apos;t run yet even when on. Add one
          in <Link to="/settings/ai">AI Settings</Link> first.
        </p>
      ) : null}

      <HuginCard />
      <Mme100Card />
    </div>
  );
}

function HuginCard() {
  const enrollment = useHuginEnrollmentQuery();
  const toggle = useSetHuginEnrollmentMutation();
  const enabled = enrollment.data?.enabled ?? false;

  return (
    <AgentCard
      mark="H"
      accent="#f97316"
      accent2="#f59e0b"
      title="HUGIN — Market Memory"
      kicker="Hourly, during market hours"
      description="Every hour the market is open, HUGIN records a short read, grades its previous read against what happened, and builds a durable memory you can review on the HUGIN tab."
      rowLabel="Hourly market memory"
      onStateLabel="On — running hourly"
      enabled={enabled}
      loading={enrollment.isLoading}
      busy={toggle.isPending}
      error={toggle.isError}
      onToggle={() => toggle.mutate(!enabled)}
    />
  );
}

function Mme100Card() {
  const enrollment = useMme100EnrollmentQuery();
  const toggle = useSetMme100EnrollmentMutation();
  const enabled = enrollment.data?.enabled ?? false;

  return (
    <AgentCard
      mark="M"
      accent="#10b981"
      accent2="#0ea5e9"
      title="MME100 — Pre-Market Analysis"
      kicker="Each trading morning, before the open"
      description="MME100 prepares a full six-section pre-market briefing — global cues, the India setup, sectors, stocks and risks — ready on the MME100 tab before the market opens."
      rowLabel="Daily pre-market briefing"
      onStateLabel="On — runs before the open"
      enabled={enabled}
      loading={enrollment.isLoading}
      busy={toggle.isPending}
      error={toggle.isError}
      onToggle={() => toggle.mutate(!enabled)}
    />
  );
}

type AgentCardProps = {
  mark: string;
  accent: string;
  accent2: string;
  title: string;
  kicker: string;
  description: ReactNode;
  rowLabel: string;
  onStateLabel: string;
  enabled: boolean;
  loading: boolean;
  busy: boolean;
  error: boolean;
  onToggle: () => void;
};

function AgentCard({
  mark,
  accent,
  accent2,
  title,
  kicker,
  description,
  rowLabel,
  onStateLabel,
  enabled,
  loading,
  busy,
  error,
  onToggle
}: AgentCardProps) {
  // Each card tones its accent (mark gradient + toggle-on colour) to its agent.
  const style = { '--agent-accent': accent, '--agent-accent-2': accent2 } as CSSProperties;

  return (
    <section className={s.card} style={style}>
      <div className={s.cardHead}>
        <span className={s.mark}>{mark}</span>
        <div>
          <h2 className={s.cardTitle}>{title}</h2>
          <span className={s.cardKicker}>{kicker}</span>
        </div>
      </div>

      <p className={s.cardDesc}>{description}</p>

      <div className={s.row}>
        <div className={s.rowText}>
          <span className={s.rowLabel}>{rowLabel}</span>
          <span className={cx(s.state, enabled ? s.stateOn : s.stateOff)}>
            {loading ? 'Loading…' : enabled ? onStateLabel : 'Off'}
          </span>
        </div>

        <button
          type="button"
          role="switch"
          aria-checked={enabled}
          aria-label={`Toggle ${title}`}
          className={cx(s.switch, enabled && s.switchOn)}
          disabled={loading || busy}
          onClick={onToggle}
        >
          <span className={s.knob} />
        </button>
      </div>

      {error ? <p className={s.error}>Couldn&apos;t save that just now — try again.</p> : null}
    </section>
  );
}
