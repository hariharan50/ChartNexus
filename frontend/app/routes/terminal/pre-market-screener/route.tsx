import { useState } from 'react';
import { usePreMarketViewQuery } from '$contexts/pre-market/queries';
import type { SectionStatus } from '$contexts/pre-market/types';
import DataSourceBadge from '$shared/ui/DataSourceBadge';
import IconSearch from '$shared/ui/icons/IconSearch';
import {
  BreadthCard,
  FlowsCard,
  GlobalCard,
  OptionsCard,
  TechnicalsGrid,
  VolatilityCard
} from './components/ContextPanels';
import ExpectedMoveCard from './components/ExpectedMoveCard';
import HeadlineCards from './components/HeadlineCards';
import LevelLadder from './components/LevelLadder';
import Panel from './components/Panel';
import RegimeScorecard from './components/RegimeScorecard';
import SectionUnavailable from './components/SectionUnavailable';
import { fmtCountdown, fmtIst, minutesToOpen } from './pms-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'PMS — Pre Market Screener · ChartNexus' }];

/**
 * PMS — the pre-market read, ordered as the decision runs.
 *
 * Someone opening this at 09:05 has about ten minutes. So it is ordered by
 * what they act on rather than by where the data came from: where are we
 * opening, how should it be read, what is the map, and only then the evidence
 * underneath. The alternative ordering — cues, then technicals, then a
 * conclusion — is how the daily PDF reads, and a PDF is read once while a
 * screener is scanned.
 *
 * Every panel carries its own status, so one dead upstream degrades one
 * section with a stated reason instead of blanking a page someone is about to
 * trade off.
 */
export default function PreMarketScreener() {
  const [focus, setFocus] = useState('NIFTY');
  const viewQ = usePreMarketViewQuery(focus);
  const view = viewQ.data;

  const countdown = view ? minutesToOpen(view.phase.time_ist, view.phase.opens_ist) : null;

  return (
    <div className={s.page}>
      <header className={s.head}>
        <div className={s.titles}>
          <h1>
            <span className={s.ico} aria-hidden="true">
              <IconSearch />
            </span>
            PMS — Pre Market Screener
          </h1>
          <p>
            The overnight context, the levels, and the conditions to watch after the open
            {view ? ` · ${view.focus_label}` : ''}
          </p>
        </div>
        <div className={s.controls}>
          {view ? (
            <span className={s.phase}>
              {view.phase.is_open
                ? 'Market open'
                : countdown !== null
                  ? `Opens in ${fmtCountdown(countdown)}`
                  : 'Market closed'}
            </span>
          ) : null}
          {view ? <DataSourceBadge source={view.source} /> : null}
          {view ? <span className={s.stamp}>as of {fmtIst(view.as_of)} IST</span> : null}
        </div>
      </header>

      {viewQ.isError ? (
        <div className={s.error} role="alert">
          <p>Couldn&apos;t load the pre-market read.</p>
          <button type="button" onClick={() => void viewQ.refetch()}>
            Retry
          </button>
        </div>
      ) : !view ? (
        <div className={s.loading}>
          <span className={s.skelWide} />
          <span className={s.skelRow} />
          <span className={s.skelRow} />
        </div>
      ) : (
        <>
          <HeadlineCards cards={view.headline} focus={view.focus} onFocus={setFocus} />

          <div className={s.pair}>
            <Panel title="Market regime" subtitle="Six axes, every input shown">
              {view.regime ? (
                <RegimeScorecard regime={view.regime} />
              ) : (
                <SectionUnavailable status={view.status.regime} />
              )}
            </Panel>

            <Panel title="Expected move" subtitle="Three measures, never blended">
              {view.expected_move ? (
                <ExpectedMoveCard move={view.expected_move} />
              ) : (
                <SectionUnavailable status={view.status.expected_move} />
              )}
            </Panel>
          </div>

          <Panel title="Key levels" subtitle={`Every reference price for ${view.focus_label}`}>
            {view.levels ? (
              <LevelLadder levels={view.levels} />
            ) : (
              <SectionUnavailable status={view.status.levels} />
            )}
          </Panel>

          <div className={s.pair}>
            <Panel title="Overnight cues" subtitle="What the world did while India slept">
              {view.global_cues ? (
                <GlobalCard read={view.global_cues} />
              ) : (
                <SectionUnavailable status={view.status.global_cues} />
              )}
            </Panel>

            <Panel title="Option positioning" subtitle="Where the book sits">
              {view.options ? (
                <OptionsCard read={view.options} />
              ) : (
                <SectionUnavailable status={view.status.options} />
              )}
            </Panel>
          </div>

          <div className={s.pair}>
            <Panel title="Technicals" subtitle={`${view.focus_label} on its own daily chart`}>
              {view.technicals ? (
                <TechnicalsGrid read={view.technicals} />
              ) : (
                <SectionUnavailable status={view.status.technicals} />
              )}
            </Panel>

            <Panel title="Volatility" subtitle="India VIX and implied volatility">
              {view.volatility ? (
                <VolatilityCard read={view.volatility} />
              ) : (
                <SectionUnavailable status={view.status.volatility} />
              )}
            </Panel>
          </div>

          <div className={s.pair}>
            <Panel title="Participation" subtitle="Breadth across the index members">
              {view.breadth ? (
                <BreadthCard read={view.breadth} />
              ) : (
                <SectionUnavailable status={view.status.breadth} />
              )}
            </Panel>

            <Panel title="Institutional flows" subtitle="Previous session, cash segment">
              {view.flows ? (
                <FlowsCard read={view.flows} />
              ) : (
                <SectionUnavailable status={view.status.flows} />
              )}
            </Panel>
          </div>

          <DegradedNote statuses={Object.entries(view.status)} />
        </>
      )}

      <p className={s.disclaimer}>
        For educational and informational purposes only. ChartNexus is not a SEBI-registered
        investment adviser. The regime score is a weighted composite with fixed, unfitted weights —
        an illustrative read, not a forecast, and markets routinely open against it. Option-OI
        levels show where positioning sits, not where price must turn. Nothing here is investment
        advice.
      </p>
    </div>
  );
}

/**
 * One line naming every panel that could not be read.
 *
 * Each panel already says so in place, but a reader scanning the page in ten
 * minutes should not have to notice a missing card to learn the read is
 * partial.
 */
function DegradedNote({ statuses }: { statuses: Array<[string, SectionStatus]> }) {
  const missing = statuses.filter(([, status]) => status.availability !== 'ok');
  if (!missing.length) return null;

  return (
    <p className={s.degraded}>
      {missing.length} of {statuses.length} panels could not be read in full:{' '}
      {missing.map(([name]) => name.replace(/_/g, ' ')).join(', ')}.
    </p>
  );
}
