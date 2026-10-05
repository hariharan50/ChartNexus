import { Fragment, useCallback, useMemo, useState } from 'react';
import type { FlowSummary, OiGroup, OiLegs, OiRow } from '$contexts/market-breadth/types';
import { useFiiDiiSummaryQuery } from '$contexts/market-breadth/queries';
import { isoDateIST } from '$shared/formatting/ist-clock';
import DataSourceBadge from '$shared/ui/DataSourceBadge';
import { SessionStatus } from '../components/SessionHeader';
import FiiDiiCharts from './components/FiiDiiCharts';
import FiiDiiGuide from './components/FiiDiiGuide';
import DatePicker from '$shared/ui/DatePicker';
import { cx } from '$shared/ui/cx';
import IconChevronDown from '$shared/ui/icons/IconChevronDown';
import IconGrid from '$shared/ui/icons/IconGrid';
import {
  FLOW_REFRESH_SECONDS,
  OI_IMBALANCE_TOLERANCE,
  PARTICIPANT_LABELS,
  SEGMENT_LABELS,
  bandLabel,
  fmtContracts,
  fmtCrore,
  fmtGross,
  fmtOiChange,
  fmtOiNet,
  fmtPercent,
  fmtPrice,
  sessionLabel,
  streakLabel,
  toNumber
} from './analysis-data';
import s from './analysis.module.css';
import p from './fii-dii-summary.module.css';
import type { Route } from './+types/fii-dii-summary';

export const meta: Route.MetaFunction = () => [
  { title: 'FII/DII Summary · Future Lab · ChartNexus' }
];

/** Which axis the open-interest board bands by. */
export type View = 'participant' | 'segment';

/** Whether the right pane shows the exact table or the charts over it. */
export type Mode = 'board' | 'charts';

/**
 * One published participant session, described completely.
 *
 * Two panes, and the split is the whole design. The left rail is **value** —
 * rupees crore traded on the day. The board is **positions** — contracts
 * held. They come from the same session and they are not the same
 * measurement: a participant can be a net buyer on the day and still hold a
 * net short book, so the two never share a table, a scale, or a unit label.
 *
 * The date stepper walks `previous_session`/`next_session` from the payload
 * rather than adding or subtracting a day. Only the source knows which days
 * the exchange published, and a client computing "yesterday" lands on the
 * first holiday it meets.
 */
export default function FiiDiiSummary() {
  // `null` means "whatever the latest published session is" — the one state a
  // date string cannot express, and the only one that should keep polling.
  const [session, setSession] = useState<string | null>(null);
  const [view, setView] = useState<View>('participant');
  // Board or charts — the same session, read as digits or as shapes.
  const [mode, setMode] = useState<Mode>('board');
  const [guideOpen, setGuideOpen] = useState(false);

  const summary = useFiiDiiSummaryQuery({ date: session });
  const data = summary.data;

  const groups = view === 'participant' ? data?.by_participant : data?.by_segment;
  const imbalanced = useMemo(
    () =>
      Object.entries(data?.imbalance ?? {}).filter(
        ([, value]) => Math.abs(value) > OI_IMBALANCE_TOLERANCE
      ),
    [data]
  );

  return (
    <div className={s.page}>
      <div className={p.layout}>
        <div className={p.rail}>
          <section className={s.card}>
            <h1 className={p.railTitle}>
              <span className={p.railIco} aria-hidden="true">
                <IconGrid />
              </span>
              FII/DII Summary
            </h1>

            <div className={p.field}>
              <span className={p.fieldLabel}>Date</span>
              <div className={p.fieldControl}>
                <DatePicker
                  value={data?.session_date ?? isoDateIST(0)}
                  max={isoDateIST(0)}
                  onChange={setSession}
                  ariaLabel="Session date"
                />
                <button
                  type="button"
                  className={p.step}
                  aria-label="Previous session"
                  disabled={!data?.previous_session}
                  onClick={() => setSession(data?.previous_session ?? null)}
                >
                  <span className={p.chevLeft} aria-hidden="true">
                    <IconChevronDown />
                  </span>
                </button>
                <button
                  type="button"
                  className={p.step}
                  aria-label="Next session"
                  // Null at the latest published day: there is no next session
                  // to show, and stepping into one would draw an empty board.
                  disabled={!data?.next_session}
                  onClick={() => setSession(data?.next_session ?? null)}
                >
                  <span className={p.chevRight} aria-hidden="true">
                    <IconChevronDown />
                  </span>
                </button>
              </div>
            </div>

            <div className={p.field}>
              <span className={p.fieldLabel}>View Mode</span>
              <div className={s.segmented} role="group" aria-label="Group the board by">
                {(['participant', 'segment'] as View[]).map((mode) => (
                  <button
                    key={mode}
                    type="button"
                    className={cx(s.segment, mode === view && s.segmentOn)}
                    aria-pressed={mode === view}
                    onClick={() => setView(mode)}
                  >
                    {mode === 'participant' ? 'Participant' : 'Segment'}
                  </button>
                ))}
              </div>
            </div>

            <div className={p.field}>
              <span className={p.fieldLabel}>Display</span>
              <div className={s.segmented} role="group" aria-label="Show the board or the charts">
                {(['board', 'charts'] as Mode[]).map((option) => (
                  <button
                    key={option}
                    type="button"
                    className={cx(s.segment, option === mode && s.segmentOn)}
                    aria-pressed={option === mode}
                    onClick={() => setMode(option)}
                  >
                    {option === 'board' ? 'Board' : 'Charts'}
                  </button>
                ))}
              </div>
            </div>
          </section>

          {data ? <ValueCard data={data} /> : null}
        </div>

        <section className={s.card}>
          <div className={s.cardHead}>
            <h2 className={s.cardTitle}>
              {mode === 'board' ? `Open interest by ${view}` : 'The session, charted'}
            </h2>
            <div className={p.headRight}>
              {/* The board only polls while it is showing the latest session —
                  an archived day cannot change — so the strip says "not
                  refreshing" there rather than counting at a settled day. */}
              <SessionStatus
                intervalSeconds={FLOW_REFRESH_SECONDS}
                active={session === null && !summary.isFetching}
                updatedAt={summary.dataUpdatedAt}
              />
              {/* Says which unit the board is in, every time. The rail beside
                  it is crores and the two are not comparable. */}
              <p className={s.cardNote}>
                {mode === 'board'
                  ? 'Contracts held, not value traded'
                  : 'Positions in contracts, flow in rupees crore'}
              </p>
              <button
                type="button"
                className={p.help}
                aria-label="How to read this page"
                title="How to read this page"
                onClick={() => setGuideOpen(true)}
              >
                ?
              </button>
            </div>
          </div>

          {summary.isError ? (
            <p className={s.error}>The participant board could not be loaded.</p>
          ) : !groups ? (
            <p className={s.placeholder}>Loading the participant file…</p>
          ) : groups.length === 0 ? (
            <p className={s.placeholder}>
              No open interest was published for {sessionLabel(data?.session_date ?? null)}.
            </p>
          ) : mode === 'charts' && data ? (
            <FiiDiiCharts data={data} />
          ) : (
            <OiBoard groups={groups} view={view} />
          )}

          {imbalanced.length > 0 ? (
            <p className={s.cardNote}>
              {imbalanced
                .map(([segment]) => SEGMENT_LABELS[segment as never] ?? segment)
                .join(', ')}{' '}
              does not sum to zero across the four participants — every long is somebody&rsquo;s
              short, so a residual means the board is incomplete.
            </p>
          ) : null}
        </section>
      </div>

      {guideOpen ? <FiiDiiGuide onClose={() => setGuideOpen(false)} /> : null}

      {data?.source === 'mock' ? (
        <p className={s.note}>
          These figures are generated, not published. The page reads NSE&rsquo;s own daily
          participant file, FII derivative statistics and cash-market activity, and none of them
          could be reached for this request — so it fell back to the simulated series rather than
          showing an empty board. The numbers behave like the real ones (positions drift rather than
          jump, and the four nets sum to zero in every segment) but describe no real session.
        </p>
      ) : null}
    </div>
  );
}

/* -- the left rail ---------------------------------------------------------- */

/** One row of the rail's value list, in rupees crore. */
interface ValueRow {
  id: string;
  name: string;
  net: number | null;
  buy: number | null;
  sell: number | null;
  /** Starts the derivative block, which sits under its own rule. */
  startsBlock?: boolean;
}

function ValueCard({ data }: { data: FlowSummary }) {
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const toggle = useCallback((id: string) => {
    setOpen((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }, []);

  const cash = data.segments.find((entry) => entry.segment === 'cash');
  const level = toNumber(data.index?.level ?? null);
  const move = toNumber(data.index?.change_percent ?? null);

  /**
   * Cash for both participants, then the FII derivative segments.
   *
   * FII only below the rule, because that is all the published value tables
   * carry: the derivative breakdown has no DII line, and inventing four dashes
   * would be four rows of nothing.
   */
  const rows: ValueRow[] = [
    {
      id: 'fii-cash',
      name: 'FII Cash Market',
      net: toNumber(cash?.fii.net ?? null),
      buy: toNumber(cash?.fii.buy ?? null),
      sell: toNumber(cash?.fii.sell ?? null)
    },
    {
      id: 'dii-cash',
      name: 'DII Cash Market',
      net: toNumber(cash?.dii?.net ?? null),
      buy: toNumber(cash?.dii?.buy ?? null),
      sell: toNumber(cash?.dii?.sell ?? null)
    },
    ...data.segments
      .filter((entry) => entry.segment !== 'cash')
      .map((entry, index) => ({
        id: `fii-${entry.segment}`,
        name: `FII ${SEGMENT_LABELS[entry.segment]}`,
        net: toNumber(entry.fii.net),
        buy: toNumber(entry.fii.buy),
        sell: toNumber(entry.fii.sell),
        startsBlock: index === 0
      }))
  ];

  return (
    <section className={s.card}>
      <p className={p.session}>{sessionLabel(data.session_date)}</p>
      {level !== null ? (
        <p className={p.benchmark}>
          Nifty {fmtPrice(level)}
          <span className={cx(p.benchmarkMove, tone(move))}>
            ({move !== null && move >= 0 ? '▲' : '▼'}
            {fmtPercent(move).replace(/^[+−-]/, '')})
          </span>
        </p>
      ) : (
        // Archived sessions carry no index level: the close for that day is
        // not stored, and today's level under yesterday's date would be worse
        // than showing none.
        <p className={p.benchmark}>Nifty —</p>
      )}
      <p className={p.unit}>(Rs. Crores)</p>

      <ul className={p.values}>
        {rows.map((row) => {
          const expanded = open.has(row.id);
          return (
            <li key={row.id} className={cx(row.startsBlock && p.valuesBreak)}>
              <button
                type="button"
                className={p.valueRow}
                aria-expanded={expanded}
                onClick={() => toggle(row.id)}
              >
                <span className={cx(p.caret, expanded && p.caretOpen)} aria-hidden="true">
                  <IconChevronDown />
                </span>
                <span className={p.valueName}>{row.name}</span>
                <span className={cx(p.valueAmount, tone(row.net))}>{fmtCrore(row.net)}</span>
              </button>
              {expanded ? (
                <div className={p.valueDetail}>
                  <span>Bought {fmtGross(row.buy)}</span>
                  <span>Sold {fmtGross(row.sell)}</span>
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>

      {cash ? (
        <div className={s.meterLegend}>
          <span>FII {streakLabel(data.fii_cash_streak)}</span>
          <span>DII {streakLabel(data.dii_cash_streak)}</span>
        </div>
      ) : (
        // The exchange archives every file on this page by date except this
        // one: cash-market value is served for the latest session only. What
        // an older session shows is therefore whatever was recorded while it
        // *was* the latest, and a dash where nothing was.
        <p className={s.cardNote}>
          No cash-market figures recorded for this session — the exchange publishes them for the
          latest session only. The derivative segments and the board below are archived and exact.
        </p>
      )}
      <DataSourceBadge source={data.source} plain />
    </section>
  );
}

/* -- the board -------------------------------------------------------------- */

/**
 * The banded board.
 *
 * Exported for `tests/component/oi-board.test.tsx`, which is where the band's
 * row-span arithmetic is pinned down — it is the one piece of this page that
 * can be silently wrong on screen without throwing.
 */
export function OiBoard({ groups, view }: { groups: OiGroup[]; view: View }) {
  const [open, setOpen] = useState<ReadonlySet<string>>(new Set());
  const toggle = useCallback((id: string) => {
    setOpen((current) => {
      const next = new Set(current);
      if (!next.delete(id)) next.add(id);
      return next;
    });
  }, []);

  const bandHeading = view === 'participant' ? 'Participant' : 'Segment';
  const rowHeading = view === 'participant' ? 'Segment' : 'Participant';

  return (
    <div className={p.board}>
      <table>
        <thead>
          <tr>
            <th scope="col">{bandHeading}</th>
            <th scope="col" className={p.rowLabel}>
              {rowHeading}
            </th>
            <th scope="col" className={p.numeric}>
              Net OI
            </th>
            <th scope="col" className={p.numeric}>
              Prev Day Net OI
            </th>
            <th scope="col" className={p.numeric}>
              Change OI
            </th>
          </tr>
        </thead>
        {groups.map((group) => (
          <Band key={group.key} group={group} view={view} open={open} onToggle={toggle} />
        ))}
      </table>
    </div>
  );
}

function Band({
  group,
  view,
  open,
  onToggle
}: {
  group: OiGroup;
  view: View;
  open: ReadonlySet<string>;
  onToggle: (id: string) => void;
}) {
  const expandedCount = group.rows.filter((row) => open.has(rowId(row))).length;

  return (
    <tbody>
      {group.rows.map((row, index) => {
        const id = rowId(row);
        const expanded = open.has(id);
        const last = index === group.rows.length - 1;
        return (
          <Fragment key={id}>
            <tr className={cx(last && !expanded && p.bandEnd)}>
              {index === 0 ? (
                // Spans its own rows *plus* any leg breakdowns currently open
                // inside the band, or the cell stops short of the group.
                <td className={p.band} rowSpan={group.rows.length + expandedCount}>
                  {bandLabel(group.key)}
                  {view === 'segment' ? (
                    // The four participants' nets must cancel — every long is
                    // somebody's short — so this reads 0 on a complete board
                    // and is worth showing as the check that it is.
                    <span className={p.bandNet}>balance {fmtOiChange(group.net)}</span>
                  ) : null}
                </td>
              ) : null}
              <td className={p.rowLabel}>
                <button
                  type="button"
                  className={p.expand}
                  aria-expanded={expanded}
                  onClick={() => onToggle(id)}
                >
                  <span className={cx(p.caret, expanded && p.caretOpen)} aria-hidden="true">
                    <IconChevronDown />
                  </span>
                  {view === 'participant'
                    ? SEGMENT_LABELS[row.segment]
                    : PARTICIPANT_LABELS[row.participant]}
                </button>
              </td>
              <td className={cx(p.numeric, tone(row.net))}>{fmtOiNet(row.net)}</td>
              {/* Coloured like the others, one shade back: yesterday is still
                  context, but a book that was short then and is short now
                  should read as one state rather than two stray numbers. */}
              <td className={cx(p.numeric, p.muted, tone(row.previous_net))}>
                {fmtOiNet(row.previous_net)}
              </td>
              <td className={cx(p.numeric, tone(row.change))}>{fmtOiChange(row.change)}</td>
            </tr>
            {expanded ? (
              <tr className={cx(p.legs, last && p.bandEnd)}>
                <td colSpan={4}>
                  <Legs legs={row.legs} />
                </td>
              </tr>
            ) : null}
          </Fragment>
        );
      })}
    </tbody>
  );
}

/**
 * The book behind a net.
 *
 * Futures carry two legs, options four. The options net is not the sum of
 * them: it is the bullish side minus the bearish one — a long call and a
 * short put both gain when the underlying rises — which is the only reason an
 * options net sits in the same column as a futures net.
 */
function Legs({ legs }: { legs: OiLegs | null }) {
  if (!legs) return <p className={s.cardNote}>No breakdown published for this row.</p>;

  // `side` is the leg's direction, not the sign of its number: a leg count is
  // always positive, so colouring it by value would paint the whole row green.
  // Bullish legs (long futures, long calls, short puts) read green, bearish red
  // — the same convention the nets above them use.
  const entries =
    legs.long !== null || legs.short !== null
      ? [
          { label: 'Long', value: legs.long, side: 'up' as const },
          { label: 'Short', value: legs.short, side: 'down' as const }
        ]
      : [
          { label: 'Call long', value: legs.call_long, side: 'up' as const },
          { label: 'Call short', value: legs.call_short, side: 'down' as const },
          { label: 'Put long', value: legs.put_long, side: 'down' as const },
          { label: 'Put short', value: legs.put_short, side: 'up' as const }
        ];

  return (
    <div className={p.legsGrid}>
      {entries.map((entry) => (
        <span className={p.leg} key={entry.label}>
          <span className={p.legLabel}>{entry.label}</span>
          <span className={cx(p.legValue, entry.side === 'up' ? s.up : s.down)}>
            {fmtContracts(entry.value)}
          </span>
        </span>
      ))}
      <span className={p.leg}>
        {/* The book's size, not a direction — left uncoloured deliberately. */}
        <span className={p.legLabel}>Total book</span>
        <span className={p.legValue}>{fmtContracts(legs.total)}</span>
      </span>
    </div>
  );
}

/** Stable across the view toggle, so an open row stays open when it regroups. */
function rowId(row: OiRow): string {
  return `${row.participant}:${row.segment}`;
}

function tone(value: number | null): string | undefined {
  if (value === null || value === 0) return undefined;
  return value > 0 ? s.up : s.down;
}
