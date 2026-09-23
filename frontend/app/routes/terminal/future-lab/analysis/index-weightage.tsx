import { useMemo, useState } from 'react';
import { DEFAULT_INDEX, type IndexId } from '$contexts/market-breadth/api';
import { useIndexWeightageQuery } from '$contexts/market-breadth/queries';
import EChart from '$shared/charts/EChart';
import { buildWeightageOption, type WeightageSlice } from '$shared/charts/options/index-weightage';
import { seriesPalette } from '$shared/charts/theme/tokens';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { cx } from '$shared/ui/cx';
import IconPie from '$shared/ui/icons/IconPie';
import { SessionStatus } from '../components/SessionHeader';
import {
  fmtPercent,
  fmtShare,
  foldToSlots,
  INDEX_REFRESH_SECONDS,
  OTHER_LABEL,
  toNumber
} from './analysis-data';
import { AnalysisHead, IndexPicker, SourceBadge } from './components/AnalysisHead';
import IndexStrip from './components/IndexStrip';
import s from './analysis.module.css';
import type { Route } from './+types/index-weightage';

export const meta: Route.MetaFunction = () => [
  { title: 'Index Weightage · Future Lab · MarketCompass' }
];

/** Which grouping the donut draws. */
type View = 'sector' | 'member';

const EMPTY: WeightageSlice[] = [];

/**
 * How the index's weight is distributed, and what that weight did today.
 *
 * The donut answers "what share of the index is this", which is the one
 * question a pie is actually good at. It is capped at eight slices, with
 * everything past the seventh folded into "Other" — folding rather than
 * truncating, so the slices still sum to the whole.
 *
 * **The table beside it is not optional.** Three of the palette's slots fall
 * below 3:1 contrast on the app's light themes, so identity has to be carried
 * by something other than colour; the labelled table is that something, and
 * removing it would break the chart's accessibility rather than just tidy the
 * layout.
 */
export default function IndexWeightage() {
  const [index, setIndex] = useState<IndexId>(DEFAULT_INDEX);
  const [view, setView] = useState<View>('sector');
  const theme = useChartTheme();
  const weightage = useIndexWeightageQuery(index);
  const data = weightage.data;

  const slices = useMemo<WeightageSlice[]>(() => {
    if (!data) return EMPTY;

    if (view === 'sector') {
      const total = data.sectors.reduce(
        (sum, sector) => sum + (toNumber(sector.weight_percent) ?? 0),
        0
      );
      const folded = foldToSlots(
        data.sectors,
        (sector) => sector.sector,
        (sector) => toNumber(sector.weight_percent) ?? 0
      );
      return folded.map((slice) => ({
        label: slice.label,
        // Re-expressed as a share of the priced index so the slices sum to
        // 100 even when the weight table does not quite.
        share: total === 0 ? 0 : (slice.value / total) * 100,
        members: slice.rows.reduce((sum, sector) => sum + sector.members.length, 0),
        changePercent: weightedMove(slice.rows)
      }));
    }

    const folded = foldToSlots(
      data.members,
      (row) => row.label,
      (row) => toNumber(row.share_percent) ?? 0
    );
    return folded.map((slice) => ({
      label: slice.label,
      share: slice.value,
      members: slice.rows.length,
      changePercent: slice.rows.length === 1 ? toNumber(slice.rows[0]!.change_percent) : null
    }));
  }, [data, view]);

  const option = useMemo(
    () =>
      buildWeightageOption(slices, theme, {
        centreLabel: view === 'sector' ? 'sectors' : 'members',
        centreValue: String(data?.header.covered ?? 0),
        formatPercent: (value: number | null) => fmtPercent(value)
      }),
    [slices, theme, view, data]
  );

  const palette = seriesPalette(theme);

  return (
    <div className={s.page}>
      <AnalysisHead
        icon={<IconPie />}
        title="Index Weightage"
        subtitle="Free-float weight by sector and by member"
      >
        <div className={s.segmented} role="group" aria-label="Group by">
          {(['sector', 'member'] as View[]).map((entry) => (
            <button
              key={entry}
              type="button"
              className={cx(s.segment, entry === view && s.segmentOn)}
              aria-pressed={entry === view}
              onClick={() => setView(entry)}
            >
              {entry === 'sector' ? 'Sector' : 'Member'}
            </button>
          ))}
        </div>
        <IndexPicker value={index} onChange={setIndex} />
        <SourceBadge source={data?.header.source} />
        <SessionStatus
          intervalSeconds={INDEX_REFRESH_SECONDS}
          active={!weightage.isFetching}
          updatedAt={weightage.dataUpdatedAt}
        />
      </AnalysisHead>

      {weightage.isError ? (
        <p className={s.error}>The weightage board could not be loaded.</p>
      ) : data === undefined ? (
        <p className={s.placeholder}>Loading the index…</p>
      ) : slices.length === 0 ? (
        <p className={s.placeholder}>No member carried a usable weight.</p>
      ) : (
        <>
          <IndexStrip header={data.header} />

          <div className={s.split}>
            <section className={s.card}>
              <div className={s.cardHead}>
                <h2 className={s.cardTitle}>Weight by {view === 'sector' ? 'sector' : 'member'}</h2>
                <p className={s.cardNote}>
                  Top {slices.length}
                  {slices.some((slice) => slice.label === OTHER_LABEL)
                    ? `, the rest folded into ${OTHER_LABEL}`
                    : ''}
                </p>
              </div>
              <EChart option={option} className={s.chart} resetKey={`${index}:${view}`} />
            </section>

            <section className={s.card}>
              <div className={s.cardHead}>
                <h2 className={s.cardTitle}>Slices</h2>
                <p className={s.cardNote}>Share of the priced index</p>
              </div>
              <div className={s.tableWrap}>
                <table className={s.table}>
                  <thead>
                    <tr>
                      <th scope="col">{view === 'sector' ? 'Sector' : 'Member'}</th>
                      <th scope="col">Share</th>
                      <th scope="col">Members</th>
                      <th scope="col">Move</th>
                    </tr>
                  </thead>
                  <tbody>
                    {slices.map((slice, position) => (
                      <tr key={slice.label}>
                        <td className={s.symbol}>
                          <span
                            className={s.swatch}
                            style={{ background: palette[position % palette.length] }}
                            aria-hidden="true"
                          />
                          {slice.label}
                        </td>
                        <td>{fmtShare(slice.share)}</td>
                        <td>{slice.members}</td>
                        <td className={cx(tone(slice.changePercent))}>
                          {fmtPercent(slice.changePercent)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </div>

          <section className={s.card}>
            <div className={s.cardHead}>
              <h2 className={s.cardTitle}>Every member</h2>
              <p className={s.cardNote}>{data.members.length} priced members, heaviest first</p>
            </div>
            <div className={s.tableWrap}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th scope="col">Symbol</th>
                    <th scope="col">Weight</th>
                    <th scope="col">Share of priced</th>
                    <th scope="col">Move</th>
                  </tr>
                </thead>
                <tbody>
                  {data.members.map((row) => (
                    <tr key={row.label}>
                      <td className={s.symbol}>
                        {row.label}
                        <span className={s.sub}>{row.name ?? '—'}</span>
                      </td>
                      <td>{fmtShare(row.weight_percent)}</td>
                      <td>{fmtShare(row.share_percent)}</td>
                      <td className={cx(tone(toNumber(row.change_percent)))}>
                        {fmtPercent(row.change_percent)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <p className={s.note}>
            Weights are free-float market capitalisation from a hand-maintained table, refreshed
            when NSE rebalances rather than daily. A stale weight shifts a slice slightly; it never
            changes a member&rsquo;s direction, which comes entirely from its price.
          </p>
        </>
      )}
    </div>
  );
}

/** Weight-averaged move across a group of sectors, or null if unmeasured. */
function weightedMove(
  sectors: { weight_percent: string | number; weighted_change_percent: string | number | null }[]
): number | null {
  let weight = 0;
  let weighted = 0;
  for (const sector of sectors) {
    const move = toNumber(sector.weighted_change_percent);
    if (move === null) continue;
    const share = toNumber(sector.weight_percent) ?? 0;
    weight += share;
    weighted += share * move;
  }
  return weight === 0 ? null : weighted / weight;
}

function tone(value: number | null): string | undefined {
  if (value === null || value === 0) return undefined;
  return value > 0 ? s.up : s.down;
}
