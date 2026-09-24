import { Fragment, useMemo } from 'react';
import type { FlowSummary } from '$contexts/market-breadth/types';
import { cx } from '$shared/ui/cx';
import {
  OI_PARTICIPANTS,
  OI_SEGMENTS,
  PARTICIPANT_LABELS,
  SEGMENT_LABELS,
  fmtContracts,
  fmtCrore,
  fmtOiNet,
  longShare,
  longShortByParticipant,
  longShortRead,
  matrixIntensity,
  moneyFlowRows,
  positioningMatrix,
  ratioVerdict
} from '../analysis-data';
import c from './FiiDiiCharts.module.css';

/**
 * The same session as pictures.
 *
 * Ordered so the page answers "how are they positioned?" before "how much did
 * they trade?" — positioning is what a reader comes to this file for, and the
 * value figures explain it rather than the other way round.
 *
 * Value and positions still never share a panel: the money flow is rupees
 * crore, everything else is contracts, and mixing them on one scale is the one
 * mistake this page exists to prevent.
 */
export default function FiiDiiCharts({ data }: { data: FlowSummary }) {
  const fii = useMemo(
    () => longShortRead(data.by_participant, 'fii', 'index_futures'),
    [data.by_participant]
  );

  const splits = useMemo(
    () => longShortByParticipant(data.by_participant, 'index_futures'),
    [data.by_participant]
  );

  const cells = useMemo(() => positioningMatrix(data.by_participant), [data.by_participant]);
  const peak = useMemo(() => Math.max(...cells.map((cell) => Math.abs(cell.net ?? 0)), 0), [cells]);

  const flows = useMemo(() => moneyFlowRows(data.segments), [data.segments]);
  const flowPeak = useMemo(
    () => Math.max(...flows.map((row) => Math.abs(row.net ?? 0)), 0),
    [flows]
  );

  const priced = splits.filter((entry) => entry.read !== undefined);

  return (
    <div className={c.grid}>
      {/*
       * 1. The headline: who is on which side of index futures.
       *
       * A split bar per participant rather than a dial. The data is a book
       * divided in two, so showing the division directly is both the honest
       * form and the readable one: "89% of the FII book is short" is a
       * proportion anyone can see, where a needle at 0.12 on an arc has to be
       * decoded first. It also has room for all four participants, which turns
       * the panel from one number into the question that actually matters —
       * who is taking the other side of the institutional trade.
       */}
      <section className={cx(c.panel, c.wide)}>
        <header className={c.head}>
          <h3 className={c.title}>Index Futures — who is on which side</h3>
          <p className={c.sub}>
            Each bar is one participant&rsquo;s futures book, split into longs and shorts.
          </p>
        </header>

        {priced.length === 0 ? (
          <p className={c.empty}>No long/short legs published for index futures this session.</p>
        ) : (
          <>
            {fii ? <p className={c.headline}>{ratioVerdict(fii)}</p> : null}

            <ul className={c.splits}>
              {splits.map(({ participant, read }) => {
                const share = read ? longShare(read) : 0;
                const pct = Math.round(share * 100);
                return (
                  <li className={c.split} key={participant}>
                    <span className={c.splitName}>{PARTICIPANT_LABELS[participant]}</span>

                    {read ? (
                      <>
                        <span
                          className={c.splitBar}
                          role="img"
                          aria-label={`${PARTICIPANT_LABELS[participant]}: ${pct}% long, ${
                            100 - pct
                          }% short`}
                        >
                          <span
                            className={cx(c.side, 'mc-up')}
                            style={{ width: `${share * 100}%` }}
                          >
                            {/* Only label the side with room for it. */}
                            {pct >= 18 ? <span className={c.sideText}>{pct}% long</span> : null}
                          </span>
                          <span
                            className={cx(c.side, 'mc-down')}
                            style={{ width: `${(1 - share) * 100}%` }}
                          >
                            {100 - pct >= 18 ? (
                              <span className={c.sideText}>{100 - pct}% short</span>
                            ) : null}
                          </span>
                        </span>

                        <span className={cx(c.splitCounts, 'mc-numeric')}>
                          <span className="mc-up">{fmtContracts(read.long)}</span>
                          <span className={c.splitSep}>vs</span>
                          <span className="mc-down">{fmtContracts(read.short)}</span>
                        </span>
                      </>
                    ) : (
                      <>
                        <span className={cx(c.splitBar, c.splitEmpty)} />
                        <span className={c.splitCounts}>not published</span>
                      </>
                    )}
                  </li>
                );
              })}
            </ul>

            <p className={c.legend}>
              <span className={cx(c.key, 'mc-up')} /> Long
              <span className={cx(c.key, 'mc-down')} /> Short
              <span className={c.legendNote}>
                A book that is mostly short is positioned for a fall.
              </span>
            </p>
          </>
        )}
      </section>

      {/* 2. Sixteen numbers as one picture. */}
      <section className={cx(c.panel, c.wide)}>
        <header className={c.head}>
          <h3 className={c.title}>Positioning matrix</h3>
          <p className={c.sub}>
            Net contracts held — green long, red short. Shaded against the largest book on the
            board, so the segments stay comparable despite differing by orders of magnitude.
          </p>
        </header>

        <div className={c.matrixScroll}>
          <div className={c.matrix}>
            <span className={c.corner} />
            {OI_SEGMENTS.map((segment) => (
              <span className={c.colHead} key={segment}>
                {SEGMENT_LABELS[segment]}
              </span>
            ))}

            {OI_PARTICIPANTS.map((participant) => (
              <Fragment key={participant}>
                <span className={c.rowHead}>{PARTICIPANT_LABELS[participant]}</span>
                {OI_SEGMENTS.map((segment) => {
                  const cell = cells.find(
                    (entry) => entry.participant === participant && entry.segment === segment
                  );
                  const net = cell?.net ?? null;
                  const intensity = matrixIntensity(net, peak);
                  const side = net === null || net === 0 ? null : net > 0 ? 'up' : 'down';
                  return (
                    <span
                      key={segment}
                      className={cx(c.cell, net === null && c.cellEmpty)}
                      style={
                        side
                          ? {
                              // Painted from the token rather than
                              // `currentcolor`, so the cell keeps white text
                              // over a coloured fill. Filled, not tinted: the
                              // floor keeps the smallest book clearly green or
                              // red instead of fading into the panel, and
                              // magnitude rides on top of it, so the grid reads
                              // as a heatmap at a glance and still ranks.
                              backgroundColor: `color-mix(in srgb, var(${
                                side === 'up' ? '--mc-bullish' : '--mc-bearish'
                              }) ${(34 + intensity * 46).toFixed(1)}%, transparent)`
                            }
                          : undefined
                      }
                      title={`${PARTICIPANT_LABELS[participant]} · ${SEGMENT_LABELS[segment]}`}
                    >
                      {fmtOiNet(net)}
                    </span>
                  );
                })}
              </Fragment>
            ))}
          </div>
        </div>
      </section>

      {/* 3. Value, kept in its own panel and its own unit. */}
      <section className={cx(c.panel, c.wide)}>
        <header className={c.head}>
          <h3 className={c.title}>Money flow</h3>
          <p className={c.sub}>
            Rupees crore traded on the day. Cash carries both participants; the derivative segments
            are FII only, because that is all the exchange publishes.
          </p>
        </header>

        <ul className={c.flows}>
          {flows.map((row) => {
            const net = row.net;
            const side = net === null || net === 0 ? null : net > 0 ? 'up' : 'down';
            const width = flowPeak > 0 && net !== null ? (Math.abs(net) / flowPeak) * 50 : 0;
            return (
              <li className={c.flowRow} key={row.id}>
                <span className={c.flowLabel}>{row.label}</span>
                <span className={c.track}>
                  <span className={c.mid} />
                  {side ? (
                    <span
                      className={cx(c.bar, side === 'up' ? 'mc-up' : 'mc-down')}
                      style={
                        net! > 0
                          ? { left: '50%', width: `${width}%` }
                          : { right: '50%', width: `${width}%` }
                      }
                    />
                  ) : null}
                </span>
                <span
                  className={cx(
                    c.flowValue,
                    'mc-numeric',
                    side === 'up' ? 'mc-up' : side === 'down' ? 'mc-down' : undefined
                  )}
                >
                  {net === null ? '—' : `${fmtCrore(net)} Cr`}
                </span>
              </li>
            );
          })}
        </ul>
      </section>
    </div>
  );
}
