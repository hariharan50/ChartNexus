import { useMemo, useState } from 'react';
import { DEFAULT_INDEX, type IndexId } from '$contexts/market-breadth/api';
import { useSectorRotationQuery } from '$contexts/market-breadth/queries';
import EChart from '$shared/charts/EChart';
import {
  buildSectorRotationOption,
  type RotationPoint
} from '$shared/charts/options/sector-rotation';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { cx } from '$shared/ui/cx';
import IconScatter from '$shared/ui/icons/IconScatter';
import { SessionStatus } from '../components/SessionHeader';
import {
  fmtPercent,
  fmtShare,
  INDEX_REFRESH_SECONDS,
  QUADRANTS,
  quadrantMeta,
  toNumber
} from './analysis-data';
import { AnalysisHead, IndexPicker, SourceBadge } from './components/AnalysisHead';
import IndexStrip from './components/IndexStrip';
import s from './analysis.module.css';
import type { Route } from './+types/sector-rotation';

export const meta: Route.MetaFunction = () => [
  { title: 'Sector Rotation · Future Lab · MarketCompass' }
];

const EMPTY: RotationPoint[] = [];

/** Border-colour class per quadrant, so the legend matches the plot. */
const QUADRANT_CLASS: Record<string, string> = {
  leading: s.quadrantLeading!,
  improving: s.quadrantImproving!,
  weakening: s.quadrantWeakening!,
  lagging: s.quadrantLagging!
};

/**
 * Where each sector sits relative to its index.
 *
 * Strength on the x axis (the sector's weight-averaged move minus the index's
 * own), participation on the y (the share of its members advancing), index
 * weight as bubble area.
 *
 * **Not a classical RRG, and the page says so.** A true relative-rotation
 * graph plots RS-Ratio against RS-*Momentum* and traces a multi-week tail
 * through the quadrants; that needs weeks of stored constituent history the
 * application does not keep yet. Participation is a defensible one-session
 * stand-in — a sector carried by a single heavyweight while everything else
 * in it sinks is a different animal from one where the whole sector is bid —
 * but it is a snapshot, so there is no tail, and the axis is labelled for what
 * it actually measures.
 */
export default function SectorRotation() {
  const [index, setIndex] = useState<IndexId>(DEFAULT_INDEX);
  const theme = useChartTheme();
  const rotation = useSectorRotationQuery(index);
  const data = rotation.data;

  const points = useMemo<RotationPoint[]>(
    () =>
      data?.sectors.map((sector) => ({
        sector: sector.sector,
        relativeStrength: toNumber(sector.relative_strength) ?? 0,
        participationOffset: toNumber(sector.participation_offset) ?? 0,
        weightPercent: toNumber(sector.weight_percent) ?? 0,
        changePercent: toNumber(sector.change_percent) ?? 0,
        advancing: sector.advancing,
        declining: sector.declining,
        members: sector.members,
        quadrant: sector.quadrant,
        leaders: sector.leaders,
        laggards: sector.laggards
      })) ?? EMPTY,
    [data]
  );

  const option = useMemo(
    () =>
      buildSectorRotationOption(points, theme, {
        formatPercent: (value: number) => fmtPercent(value)
      }),
    [points, theme]
  );

  return (
    <div className={s.page}>
      <AnalysisHead
        icon={<IconScatter />}
        title="Sector Rotation"
        subtitle="Each sector's strength and participation against its index"
      >
        <IndexPicker value={index} onChange={setIndex} />
        <SourceBadge source={data?.header.source} />
        <SessionStatus
          intervalSeconds={INDEX_REFRESH_SECONDS}
          active={!rotation.isFetching}
          updatedAt={rotation.dataUpdatedAt}
        />
      </AnalysisHead>

      {rotation.isError ? (
        <p className={s.error}>The rotation board could not be loaded.</p>
      ) : data === undefined ? (
        <p className={s.placeholder}>Loading the index…</p>
      ) : points.length === 0 ? (
        <p className={s.placeholder}>
          No sector could be priced, so there is nothing to place on the grid.
        </p>
      ) : (
        <>
          <IndexStrip header={data.header} />

          <section className={s.card}>
            <div className={s.cardHead}>
              <h2 className={s.cardTitle}>Strength against participation</h2>
              <p className={s.cardNote}>Bubble area is index weight · {points.length} sectors</p>
            </div>
            <div className={s.quadrants}>
              {QUADRANTS.map((quadrant) => (
                <div key={quadrant.id} className={cx(s.quadrant, QUADRANT_CLASS[quadrant.id])}>
                  <span className={s.quadrantName}>
                    {quadrant.label} ·{' '}
                    {points.filter((point) => point.quadrant === quadrant.id).length}
                  </span>
                  <span className={s.quadrantHint}>{quadrant.hint}</span>
                </div>
              ))}
            </div>
            <EChart option={option} className={s.chartTall} resetKey={index} />
          </section>

          <section className={s.card}>
            <div className={s.cardHead}>
              <h2 className={s.cardTitle}>Sectors</h2>
              <p className={s.cardNote}>Heaviest first</p>
            </div>
            <div className={s.tableWrap}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th scope="col">Sector</th>
                    <th scope="col">Move</th>
                    <th scope="col">vs index</th>
                    <th scope="col">Advancing</th>
                    <th scope="col">Weight</th>
                    <th scope="col">Quadrant</th>
                  </tr>
                </thead>
                <tbody>
                  {points.map((point) => (
                    <tr key={point.sector}>
                      <td className={s.symbol}>
                        {point.sector}
                        <span className={s.sub}>
                          {point.leaders.length ? `↑ ${point.leaders.join(', ')}` : '—'}
                        </span>
                      </td>
                      <td className={cx(tone(point.changePercent))}>
                        {fmtPercent(point.changePercent)}
                      </td>
                      <td className={cx(tone(point.relativeStrength))}>
                        {fmtPercent(point.relativeStrength)}
                      </td>
                      <td>
                        {point.advancing} / {point.members}
                      </td>
                      <td>{fmtShare(point.weightPercent)}</td>
                      <td>{quadrantMeta(point.quadrant).label}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <p className={s.note}>
            A single session, not a rotation trail. The vertical axis is participation — the share
            of a sector&rsquo;s members advancing — rather than the rate of change of relative
            strength a classical RRG plots, because that needs weeks of stored constituent history
            this application does not keep yet.
          </p>
        </>
      )}
    </div>
  );
}

function tone(value: number): string | undefined {
  if (value === 0) return undefined;
  return value > 0 ? s.up : s.down;
}
