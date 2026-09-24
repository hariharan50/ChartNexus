import { useGlobalViewQuery } from '$contexts/global-markets/queries';
import DataSourceBadge from '$shared/ui/DataSourceBadge';
import IconGlobe from '$shared/ui/icons/IconGlobe';
import GapPressureGauge from './components/GapPressureGauge';
import HandoffTimeline from './components/HandoffTimeline';
import ImpliedOpenCard from './components/ImpliedOpenCard';
import IndexBoard from './components/IndexBoard';
import MacroStrip from './components/MacroStrip';
import { fmtDay, fmtIst } from './gia-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [
  { title: 'GIA — Global Index Analysis · MarketCompass' }
];

/**
 * GIA — the overnight handoff, read as one story.
 *
 * The page is ordered as the inference runs, not as the data arrives: the
 * timeline shows what happened and in what order, the composite weighs it, the
 * implied open quotes it directly, and the board is the evidence underneath.
 * Reading top to bottom should answer "where does NIFTY open, and why".
 */
export default function GlobalIndexAnalysis() {
  const viewQ = useGlobalViewQuery();
  const view = viewQ.data;

  return (
    <div className={s.page}>
      <header className={s.head}>
        <div className={s.titles}>
          <h1>
            <span className={s.ico} aria-hidden="true">
              <IconGlobe />
            </span>
            GIA — Global Index Analysis
          </h1>
          <p>
            What the world did while India slept, and the open it implies
            {view ? ` · for ${fmtDay(view.window.closes_at)}` : ''}
          </p>
        </div>
        <div className={s.controls}>
          {view ? <DataSourceBadge source={view.source} /> : null}
          {view ? <span className={s.stamp}>as of {fmtIst(view.as_of)} IST</span> : null}
        </div>
      </header>

      {viewQ.isError ? (
        <div className={s.error} role="alert">
          <p>Couldn&apos;t load the global board.</p>
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
          <HandoffTimeline window={view.window} bands={view.bands} />

          <div className={s.reads}>
            <GapPressureGauge pressure={view.pressure} />
            <ImpliedOpenCard
              implied={view.implied}
              verdict={view.verdict}
              source={view.gift_source}
            />
          </div>

          <IndexBoard markets={view.markets} regions={view.regions} labels={view.region_labels} />

          <MacroStrip markets={view.markets} />
        </>
      )}

      <p className={s.disclaimer}>
        For educational and informational purposes only. MarketCompass is not a SEBI-registered
        investment adviser. Gap pressure is a weighted composite of overnight index moves with
        fixed, unfitted weights — it is an illustrative read, not a forecast, and markets routinely
        open against it. Nothing here is investment advice.
      </p>
    </div>
  );
}
