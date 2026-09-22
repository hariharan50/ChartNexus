import { useMemo, useState } from 'react';
import { DEFAULT_INDEX, type IndexId } from '$contexts/market-breadth/api';
import { useAdvanceDeclineQuery } from '$contexts/market-breadth/queries';
import type { BreadthCount } from '$contexts/market-breadth/types';
import EChart from '$shared/charts/EChart';
import {
  buildSectorBreadthOption,
  type SectorBreadthBar
} from '$shared/charts/options/sector-breadth';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { cx } from '$shared/ui/cx';
import IconArea from '$shared/ui/icons/IconArea';
import { RefreshRing } from '../components/SessionHeader';
import {
  fmtPercent,
  fmtPrice,
  fmtShare,
  INDEX_REFRESH_SECONDS,
  ratioLabel,
  toNumber
} from './analysis-data';
import { AnalysisHead, IndexPicker, SourceBadge } from './components/AnalysisHead';
import IndexStrip from './components/IndexStrip';
import s from './analysis.module.css';
import type { Route } from './+types/advance-decline';

export const meta: Route.MetaFunction = () => [
  { title: 'Advance Decline · Future Lab · MarketCompass' }
];

const EMPTY: SectorBreadthBar[] = [];

/**
 * How broad the index's move actually is.
 *
 * The index level says where the benchmark went; breadth says how many of its
 * members went with it. A 0.6% rise on 12 of 50 advancing is a different
 * session from the same rise on 40 of 50, and the two are indistinguishable
 * from the level alone.
 *
 * Three distinctions the page refuses to blur:
 *
 * * **Unchanged is not a direction.** A member inside the deadband is flat,
 *   not up, and it gets the neutral ink.
 * * **Unpriced is not unchanged.** A member the feed could not price is
 *   counted apart and named in the caption.
 * * **The sector bars are proportions, not counts.** Sectors are different
 *   sizes, and stacking raw counts would let the biggest one answer a question
 *   nobody asked.
 */
export default function AdvanceDecline() {
  const [index, setIndex] = useState<IndexId>(DEFAULT_INDEX);
  const theme = useChartTheme();
  const breadth = useAdvanceDeclineQuery(index);
  const data = breadth.data;

  const bars = useMemo<SectorBreadthBar[]>(
    () =>
      data?.sectors.map((sector) => ({
        sector: sector.sector,
        advancing: sector.count.advancing,
        declining: sector.count.declining,
        unchanged: sector.count.unchanged,
        weightPercent: toNumber(sector.weight_percent) ?? 0,
        changePercent: toNumber(sector.weighted_change_percent)
      })) ?? EMPTY,
    [data]
  );

  const option = useMemo(
    () =>
      buildSectorBreadthOption(bars, theme, {
        formatPercent: (value: number | null) => fmtPercent(value)
      }),
    [bars, theme]
  );

  return (
    <div className={s.page}>
      <AnalysisHead
        icon={<IconArea />}
        title="Advance Decline"
        subtitle="How many index members are up, down and flat"
      >
        <IndexPicker value={index} onChange={setIndex} />
        <SourceBadge source={data?.header.source} />
        <RefreshRing seconds={INDEX_REFRESH_SECONDS} active={!breadth.isFetching} />
      </AnalysisHead>

      {breadth.isError ? (
        <p className={s.error}>The breadth reading could not be loaded.</p>
      ) : data === undefined ? (
        <p className={s.placeholder}>Loading the index…</p>
      ) : (
        <>
          <IndexStrip header={data.header} />

          <section className={s.card}>
            <div className={s.cardHead}>
              <h2 className={s.cardTitle}>Index breadth</h2>
              <p className={s.cardNote}>
                {ratioLabel(data.overall)} advance/decline
                {data.overall.unpriced > 0 ? ` · ${data.overall.unpriced} unpriced` : ''}
              </p>
            </div>
            <Meter count={data.overall} />
            <p className={s.meterLegend}>
              <span>
                <span
                  className={s.swatch}
                  style={{ background: 'var(--mc-bullish)' }}
                  aria-hidden="true"
                />
                Advancing {data.overall.advancing}
              </span>
              <span>
                <span
                  className={s.swatch}
                  style={{ background: 'var(--mc-neutral)' }}
                  aria-hidden="true"
                />
                Unchanged {data.overall.unchanged}
              </span>
              <span>
                <span
                  className={s.swatch}
                  style={{ background: 'var(--mc-bearish)' }}
                  aria-hidden="true"
                />
                Declining {data.overall.declining}
              </span>
            </p>
          </section>

          {bars.length > 0 ? (
            <section className={s.card}>
              <div className={s.cardHead}>
                <h2 className={s.cardTitle}>By sector</h2>
                <p className={s.cardNote}>
                  Share of each sector&rsquo;s members, heaviest sector first
                </p>
              </div>
              <EChart option={option} className={s.chartTall} resetKey={index} />
            </section>
          ) : null}

          <section className={s.card}>
            <div className={s.cardHead}>
              <h2 className={s.cardTitle}>Members</h2>
              <p className={s.cardNote}>Heaviest first · {data.members.length} rows</p>
            </div>
            <div className={s.tableWrap}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th scope="col">Symbol</th>
                    <th scope="col">Last</th>
                    <th scope="col">Change</th>
                    <th scope="col">%</th>
                    <th scope="col">Weight</th>
                  </tr>
                </thead>
                <tbody>
                  {data.members.map((member) => {
                    const move = toNumber(member.change_percent);
                    return (
                      <tr key={member.symbol}>
                        <td className={s.symbol}>
                          {member.symbol}
                          <span className={s.sub}>{member.sector ?? '—'}</span>
                        </td>
                        <td>{fmtPrice(member.last)}</td>
                        <td className={cx(tone(toNumber(member.change_absolute)))}>
                          {fmtPrice(member.change_absolute)}
                        </td>
                        <td className={cx(tone(move))}>{fmtPercent(member.change_percent)}</td>
                        <td>{fmtShare(member.weight_percent)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}

/**
 * The whole index as one bar.
 *
 * Proportional widths, in the three states' own colours, with the counts
 * written beside it — colour alone never carries the reading.
 */
function Meter({ count }: { count: BreadthCount }) {
  const total = count.advancing + count.declining + count.unchanged;
  const width = (part: number) => (total === 0 ? 0 : (part / total) * 100);

  return (
    <div
      className={s.meter}
      role="img"
      aria-label={`${count.advancing} advancing, ${count.unchanged} unchanged, ${count.declining} declining`}
    >
      <span
        className={cx(s.meterPart, s.meterAdv)}
        style={{ width: `${width(count.advancing)}%` }}
      />
      <span
        className={cx(s.meterPart, s.meterUnch)}
        style={{ width: `${width(count.unchanged)}%` }}
      />
      <span
        className={cx(s.meterPart, s.meterDec)}
        style={{ width: `${width(count.declining)}%` }}
      />
    </div>
  );
}

function tone(value: number | null): string | undefined {
  if (value === null || value === 0) return undefined;
  return value > 0 ? s.up : s.down;
}
