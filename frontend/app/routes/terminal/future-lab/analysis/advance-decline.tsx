import { useMemo, useState } from 'react';
import {
  DEFAULT_BREADTH_INTERVAL,
  DEFAULT_INDEX,
  INDICES,
  type BreadthInterval
} from '$contexts/market-breadth/api';
import {
  useAdvanceDeclineQuery,
  useBreadthSeriesQuery,
  useSectorRailQuery
} from '$contexts/market-breadth/queries';
import type { BreadthSeries, IndexMember, SectorRow } from '$contexts/market-breadth/types';
import EChart from '$shared/charts/EChart';
import {
  buildAdvanceDeclineSeriesOption,
  type BreadthSeriesPoint
} from '$shared/charts/options/advance-decline-series';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import DataSourceBadge from '$shared/ui/DataSourceBadge';
import IconArea from '$shared/ui/icons/IconArea';
import { isoDateIST } from '$shared/formatting/ist-clock';
import { SessionStatus } from '../components/SessionHeader';
import { fmtPercent, fmtPrice, INDEX_REFRESH_SECONDS, ratioLabel, toNumber } from './analysis-data';
import { AnalysisHead, SourceBadge } from './components/AnalysisHead';
import BreadthControls, { type BreadthMode } from './components/BreadthControls';
import BreadthRail, { type Scope } from './components/BreadthRail';
import DivergingBoard, { type BoardRow } from './components/DivergingBoard';
import s from './analysis.module.css';
import type { Route } from './+types/advance-decline';

export const meta: Route.MetaFunction = () => [
  { title: 'Advance Decline · Future Lab · MarketCompass' }
];

const NO_SECTORS: SectorRow[] = [];
const NO_MEMBERS: IndexMember[] = [];

/**
 * How broad a move is, through the session rather than at this instant.
 *
 * The index level says where the benchmark went; breadth says how many of its
 * members went with it. A 0.6% rise on 12 of 50 advancing is a different
 * session from the same rise on 40 of 50, and the level alone cannot tell them
 * apart — nor can a single point-in-time count tell you *when* the rally
 * narrowed.
 *
 * Three things this page refuses to blur:
 *
 * * **Two universes, named.** The rail's index rows count a published index
 *   against published weights; its sector rows count every F&O name the
 *   catalog classifies there. Those numbers are not comparable and the
 *   headings say so.
 * * **A sector has no price and no weight.** There is no NIFTY IT here, so no
 *   level is drawn for a sector and the weighted view is disabled rather than
 *   shown flat.
 * * **The series says what it is worth.** Counted out of the captured board,
 *   so `live_proxy` — two points joined by a straight line — is labelled, not
 *   dressed up as a session.
 */
export default function AdvanceDecline() {
  const theme = useChartTheme();
  const [scope, setScope] = useState<Scope>({ index: DEFAULT_INDEX, sector: null });
  const [interval, setInterval] = useState<BreadthInterval>(DEFAULT_BREADTH_INTERVAL);
  const [mode, setMode] = useState<BreadthMode>('live');
  const [date, setDate] = useState<string>(isoDateIST(0));
  const [weighted, setWeighted] = useState(false);

  const rail = useSectorRailQuery();
  const breadth = useAdvanceDeclineQuery(scope.index);
  const series = useBreadthSeriesQuery({
    index: scope.index,
    sector: scope.sector,
    date: mode === 'historical' ? date : null,
    interval
  });

  const sectors = rail.data?.sectors ?? NO_SECTORS;
  const sessions = rail.data?.sessions ?? [];
  const data = series.data;
  const weightedAvailable = data?.weighted_available ?? false;
  const plotWeighted = weighted && weightedAvailable;

  const points = useMemo<BreadthSeriesPoint[]>(
    () =>
      (data?.points ?? []).map((point) => ({
        at: point.at,
        advancing: point.advancing,
        declining: point.declining,
        level: toNumber(point.level),
        advancingWeight: toNumber(point.advancing_weight),
        decliningWeight: toNumber(point.declining_weight)
      })),
    [data]
  );

  const option = useMemo(
    () =>
      buildAdvanceDeclineSeriesOption(points, theme, {
        weighted: plotWeighted,
        levelName: scope.sector === null ? indexLabel(scope.index) : null,
        formatTime: clockLabel,
        formatLevel: (value: number) => fmtPrice(value)
      }),
    [points, theme, plotWeighted, scope]
  );

  /** The scope's own names, for the board under the chart. */
  const members = useMemo<IndexMember[]>(() => {
    if (scope.sector === null) return breadth.data?.members ?? NO_MEMBERS;
    return sectors.find((row) => row.sector === scope.sector)?.rows ?? NO_MEMBERS;
  }, [scope, breadth.data, sectors]);

  const up = useMemo(() => members.filter(isUp).map(toRow), [members]);
  const down = useMemo(() => members.filter(isDown).map(toRow), [members]);
  const scopeLabel = data?.label ?? indexLabel(scope.index);

  return (
    <div className={s.page}>
      <AnalysisHead
        icon={<IconArea />}
        title="Advance Decline"
        subtitle="How many members were up, down and flat — through the session"
      >
        <SourceBadge source={breadth.data?.header.source} />
        <SessionStatus
          intervalSeconds={INDEX_REFRESH_SECONDS}
          active={!series.isFetching && !rail.isFetching}
          // Two queries feed this page, so the honest age is the older of
          // them: the screen is only as fresh as its stalest half.
          updatedAt={Math.min(series.dataUpdatedAt, rail.dataUpdatedAt) || undefined}
        />
      </AnalysisHead>

      <BreadthControls
        interval={interval}
        onInterval={setInterval}
        mode={mode}
        onMode={setMode}
        date={date}
        onDate={setDate}
        sessions={sessions}
        weighted={weighted}
        onWeighted={setWeighted}
        weightedAvailable={weightedAvailable}
      />

      <div className={s.breadthRow}>
        <BreadthRail
          scope={scope}
          onScope={setScope}
          sectors={sectors}
          header={breadth.data?.header}
          loading={rail.isLoading}
        />

        <div className={s.breadthMain}>
          <section className={s.card}>
            <div className={s.cardHead}>
              <h2 className={s.cardTitle}>{scopeLabel} Advance / Decline</h2>
              <p className={s.cardNote}>{qualityNote(data)}</p>
            </div>

            {series.isError ? (
              <p className={s.error}>The breadth series could not be loaded.</p>
            ) : points.length === 0 ? (
              <p className={s.placeholder}>
                {series.isLoading
                  ? 'Counting the session…'
                  : 'No session has been captured for this scope yet.'}
              </p>
            ) : (
              <EChart
                option={option}
                className={s.chart}
                resetKey={`${scope.index}:${scope.sector}:${interval}`}
              />
            )}

            {data?.source ? <DataSourceBadge source={data.source} /> : null}
          </section>

          <DivergingBoard
            title={`${scopeLabel} Stocks Change %`}
            totals={
              <>
                <span className={s.up}>{up.length} ↑</span>
                <span className={s.down}>{down.length} ↓</span>
              </>
            }
            note={breadth.data ? `${ratioLabel(breadth.data.overall)} advance/decline` : undefined}
            up={up}
            down={down}
            format={(value) => fmtPercent(value)}
          />
        </div>
      </div>
    </div>
  );
}

/** `2:36 PM` — exchange-local, because a session is an IST fact. */
function clockLabel(iso: string): string {
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return new Intl.DateTimeFormat('en-IN', {
    timeZone: 'Asia/Kolkata',
    hour: 'numeric',
    minute: '2-digit',
    hour12: true
  }).format(parsed);
}

/**
 * What the chart above is worth, in one line.
 *
 * Never omitted. A two-point proxy and a captured session look identical once
 * they are drawn, and this is the only thing that separates them.
 */
function qualityNote(series: BreadthSeries | undefined): string {
  if (!series) return '';
  const scope = `${series.measured} of ${series.universe} priced`;
  if (series.quality === 'live_proxy') {
    return `${scope} · previous close vs now — the shape between them was not captured`;
  }
  if (series.quality === 'empty') return `${scope} · nothing captured for this session`;
  const basis = series.baseline === 'previous_close' ? 'previous close' : "prior session's close";
  return `${scope} · ${series.interval} buckets · against ${basis}`;
}

function indexLabel(index: string): string {
  return INDICES.find((entry) => entry.id === index)?.label ?? index;
}

function isUp(member: IndexMember): boolean {
  return (toNumber(member.change_percent) ?? 0) > 0;
}

function isDown(member: IndexMember): boolean {
  return (toNumber(member.change_percent) ?? 0) < 0;
}

function toRow(member: IndexMember): BoardRow {
  const change = toNumber(member.change_percent) ?? 0;
  return {
    symbol: member.symbol,
    value: change,
    hover: [member.name ?? member.symbol, fmtPercent(change), fmtPrice(member.last)].join(' · ')
  };
}
