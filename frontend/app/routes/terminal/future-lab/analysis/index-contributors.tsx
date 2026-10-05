import { useMemo, useState } from 'react';
import { DEFAULT_INDEX, INDICES, type IndexId } from '$contexts/market-breadth/api';
import { useIndexContributorsQuery } from '$contexts/market-breadth/queries';
import type { Contribution } from '$contexts/market-breadth/types';
import EChart from '$shared/charts/EChart';
import {
  buildContributorsOption,
  type ContributionBar
} from '$shared/charts/options/index-contributors';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import IconBars from '$shared/ui/icons/IconBars';
import { SessionStatus } from '../components/SessionHeader';
import { fmtPercent, fmtPoints, INDEX_REFRESH_SECONDS, toNumber } from './analysis-data';
import { AnalysisHead, IndexPicker, SourceBadge } from './components/AnalysisHead';
import ContributorList from './components/ContributorList';
import IndexStrip from './components/IndexStrip';
import PointsContribution from './components/PointsContribution';
import s from './analysis.module.css';
import type { Route } from './+types/index-contributors';

export const meta: Route.MetaFunction = () => [
  { title: 'Index Contributors · Future Lab · ChartNexus' }
];

/** How many names each side of the chart shows. Beyond this the bars are dust. */
const SIDE_LIMIT = 10;

const EMPTY: Contribution[] = [];

/**
 * Who moved the index, in index points.
 *
 * `points = weight/100 × change%/100 × previous index level`, with the priced
 * members' weights renormalised to sum to 100 so the bars add up to the number
 * in the header. The residual against the index's own move is published as
 * "unexplained" rather than hidden — on a fully priced index it is near zero,
 * and when it is not, that is a fact about the data.
 */
export default function IndexContributors() {
  const [index, setIndex] = useState<IndexId>(DEFAULT_INDEX);
  const theme = useChartTheme();
  const contributors = useIndexContributorsQuery(index);
  const data = contributors.data;

  const gainers = data?.gainers ?? EMPTY;
  const losers = data?.losers ?? EMPTY;

  /**
   * The chart's rows: the biggest pushes at the top, the biggest drags at the
   * bottom, and nothing in between. The middle of this distribution is dozens
   * of names contributing a hundredth of a point each — drawing them would
   * turn a readable chart into a picket fence.
   */
  const bars = useMemo<ContributionBar[]>(() => {
    const toBar = (row: Contribution): ContributionBar => ({
      symbol: row.symbol,
      points: toNumber(row.points) ?? 0,
      changePercent: toNumber(row.change_percent) ?? 0,
      weightPercent: toNumber(row.weight_percent) ?? 0
    });
    return [
      ...gainers.slice(0, SIDE_LIMIT).map(toBar),
      ...losers.slice(0, SIDE_LIMIT).reverse().map(toBar)
    ];
  }, [gainers, losers]);

  const option = useMemo(
    () =>
      buildContributorsOption(bars, theme, {
        formatPoints: (value: number) => fmtPoints(value),
        formatPercent: (value: number) => fmtPercent(value)
      }),
    [bars, theme]
  );

  return (
    <div className={s.page}>
      <AnalysisHead
        icon={<IconBars />}
        title="Index Contributors"
        subtitle="Index points each member pushed or dragged the index"
      >
        <IndexPicker value={index} onChange={setIndex} />
        <SourceBadge source={data?.header.source} />
        <SessionStatus
          intervalSeconds={INDEX_REFRESH_SECONDS}
          active={!contributors.isFetching}
          updatedAt={contributors.dataUpdatedAt}
        />
      </AnalysisHead>

      {contributors.isError ? (
        <p className={s.error}>The contributors board could not be loaded.</p>
      ) : data === undefined ? (
        <p className={s.placeholder}>Loading the index…</p>
      ) : bars.length === 0 ? (
        <p className={s.placeholder}>
          No member could be priced against a previous close, so no contribution can be computed.
        </p>
      ) : (
        <>
          <IndexStrip header={data.header} />

          {/*
            One side of the index, the board, the other side. The lists say
            where each member is; the board says how much it moved the index.
            Side by side because they are read together — a name that surprises
            you on the board is one glance away from its own price.
          */}
          <div className={s.boardRow}>
            <ContributorList title="Positive Contributors" rows={gainers} side="up" />
            <PointsContribution label={indexLabel(index)} gainers={gainers} losers={losers} />
            <ContributorList title="Negative Contributors" rows={losers} side="down" />
          </div>

          <section className={s.card}>
            <div className={s.cardHead}>
              <h2 className={s.cardTitle}>
                Top {Math.min(SIDE_LIMIT, gainers.length)} contributors and{' '}
                {Math.min(SIDE_LIMIT, losers.length)} detractors
              </h2>
              <p className={s.cardNote}>
                Modelled {fmtPoints(data.modelled_points)} pts of {fmtPoints(data.actual_points)}{' '}
                pts
                {data.gap === null ? '' : ` · ${fmtPoints(data.gap)} unexplained`}
              </p>
            </div>
            <EChart option={option} className={s.chartTall} resetKey={index} />
          </section>
        </>
      )}
    </div>
  );
}

/** How the picker spells this index — "NIFTY 50", not "NIFTY50". */
function indexLabel(index: IndexId): string {
  return INDICES.find((entry) => entry.id === index)?.label ?? index;
}
