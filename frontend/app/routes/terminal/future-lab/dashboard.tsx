import { useMemo, useState } from 'react';
import {
  useFuturesBoardQuery,
  useFuturesDashboardQuery
} from '$contexts/futures-analytics/queries';
import type { FuturesRow } from '$contexts/futures-analytics/types';
import DataTable, { type Column } from '$shared/ui/DataTable';
import { cx } from '$shared/ui/cx';
import ExpiryPicker from './components/ExpiryPicker';
import {
  COMPARE_WINDOWS,
  PANELS,
  PENDING_WINDOW_HINT,
  direction,
  fmtOi,
  fmtPercent,
  fmtPrice,
  sectorsIn,
  stateLabel,
  toNumber,
  type CompareWindow,
  type PanelTone
} from './dashboard-data';
import s from './dashboard.module.css';
import type { Route } from './+types/dashboard';

export const meta: Route.MetaFunction = () => [
  { title: 'Future Dashboard · Future Lab · MarketCompass' }
];

const PANEL_ROWS = 5;

/** Stable identity, so memos downstream of it do not rerun every render. */
const NO_ROWS: FuturesRow[] = [];

type View = 'panels' | 'table';

export default function FutureDashboard() {
  const [view, setView] = useState<View>('panels');
  const [compare, setCompare] = useState<CompareWindow>('prev');
  const [sector, setSector] = useState<string>('');
  // 0 is the near month. Held here rather than inside the toolbar because both
  // the panels and the table read it, and they must never disagree about which
  // contract they are describing.
  const [series, setSeries] = useState(0);

  const panels = useFuturesDashboardQuery({
    limit: PANEL_ROWS,
    series,
    ...(sector ? { sector } : {})
  });
  // Only fetched once the table view is actually open: it is the whole
  // universe, and the panels already cost a board read.
  const board = useFuturesBoardQuery(
    view === 'table' ? { series, ...(sector ? { sector } : {}) } : { series }
  );

  const rows = view === 'table' ? (board.data?.rows ?? NO_ROWS) : NO_ROWS;
  const sectors = useMemo(() => sectorsIn(rows), [rows]);

  const covered = panels.data?.covered ?? 0;
  const universe = panels.data?.universe ?? 0;
  const partial = universe > 0 && covered < universe;

  return (
    <div className={s.page}>
      <header className={s.header}>
        <div>
          <h1 className={s.title}>Future Dashboard</h1>
          <p className={s.subtitle}>
            F&amp;O futures across the universe, classified by price against open interest. Pick the
            contract with the expiry control.
          </p>
        </div>

        <div className={s.viewToggle} role="group" aria-label="View">
          <button
            type="button"
            className={cx(s.toggleBtn, view === 'panels' && s.toggleOn)}
            aria-pressed={view === 'panels'}
            onClick={() => setView('panels')}
          >
            Panels
          </button>
          <button
            type="button"
            className={cx(s.toggleBtn, view === 'table' && s.toggleOn)}
            aria-pressed={view === 'table'}
            onClick={() => setView('table')}
          >
            All contracts
          </button>
        </div>
      </header>

      <div className={s.toolbar}>
        <ExpiryPicker
          series={series}
          onSeries={setSeries}
          resolved={panels.data?.expiry}
          hasOpenInterest={panels.data?.has_open_interest}
        />

        <div className={s.compare}>
          <span className={s.toolLabel} id="compare-label">
            Compare
          </span>
          <div className={s.segmented} role="group" aria-labelledby="compare-label">
            {COMPARE_WINDOWS.map((window) => (
              <button
                key={window.id}
                type="button"
                className={cx(s.segment, compare === window.id && s.segmentOn)}
                aria-pressed={compare === window.id}
                disabled={!window.available}
                title={window.available ? undefined : PENDING_WINDOW_HINT}
                onClick={() => setCompare(window.id)}
              >
                {window.label}
              </button>
            ))}
          </div>
        </div>

        {/* Sectors are not carried by the exchange symbol master, so the filter
            appears only once some other source has populated them. */}
        {sectors.length > 0 ? (
          <label className={s.sector}>
            <span className={s.toolLabel}>Sector</span>
            <select
              className={s.select}
              value={sector}
              onChange={(event) => setSector(event.currentTarget.value)}
            >
              <option value="">All sectors</option>
              {sectors.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        ) : null}

        <span className={s.coverage}>
          {universe > 0 ? (
            <>
              {covered} of {universe} contracts
              {partial ? <span className={s.partial}> · partial board</span> : null}
            </>
          ) : null}
        </span>
      </div>

      {/* Four empty build-up panels are a claim about the market, so when they
          are empty for a different reason the page has to say which. */}
      {panels.data && panels.data.has_open_interest === false ? (
        <p className={s.notice}>
          Open interest is not swept for this contract, so the four build-up panels are empty
          because nothing was measured — not because nothing is building. Prices, volume and the
          day&rsquo;s range are the contract&rsquo;s own.
        </p>
      ) : null}

      {panels.isError ? <p className={s.error}>The futures board could not be loaded.</p> : null}

      {view === 'panels' ? (
        <div className={s.grid}>
          {PANELS.map((panel) => (
            <Panel
              key={panel.key}
              title={panel.title}
              tone={panel.tone}
              rows={panels.data?.[panel.key] ?? []}
              loading={panels.isLoading}
            />
          ))}
        </div>
      ) : (
        <BoardTable rows={rows} loading={board.isLoading} />
      )}
    </div>
  );
}

function Panel({
  title,
  tone,
  rows,
  loading
}: {
  title: string;
  tone: PanelTone;
  rows: FuturesRow[];
  loading: boolean;
}) {
  return (
    <section className={cx(s.panel, tone === 'up' ? s.panelUp : s.panelDown)}>
      <h2 className={s.panelTitle}>{title}</h2>
      {loading ? (
        <p className={s.panelEmpty}>Loading…</p>
      ) : rows.length === 0 ? (
        <p className={s.panelEmpty}>No contracts in this state.</p>
      ) : (
        <table className={s.panelTable}>
          <thead>
            <tr>
              <th scope="col">Symbol</th>
              <th scope="col" className={s.num}>
                Price
              </th>
              <th scope="col" className={s.num}>
                OI
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.symbol}>
                <th scope="row" className={s.symbol} title={row.name ?? undefined}>
                  {row.symbol}
                </th>
                <td className={cx(s.num, toneClass(row.price_change_percent))}>
                  {fmtPercent(row.price_change_percent)}
                </td>
                <td className={cx(s.num, toneClass(row.oi_change_percent))}>
                  {fmtPercent(row.oi_change_percent)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}

function BoardTable({ rows, loading }: { rows: FuturesRow[]; loading: boolean }) {
  const columns: Column<FuturesRow>[] = useMemo(
    () => [
      {
        key: 'symbol',
        header: 'Symbol',
        render: (row) => (
          <span className={s.symbol} title={row.name ?? undefined}>
            {row.symbol}
          </span>
        ),
        sortValue: (row) => row.symbol
      },
      {
        key: 'price',
        header: 'Price',
        align: 'right',
        render: (row) => fmtPrice(row.price),
        sortValue: (row) => toNumber(row.price)
      },
      {
        key: 'price_change',
        header: 'Price %',
        align: 'right',
        render: (row) => (
          <span className={toneClass(row.price_change_percent)}>
            {fmtPercent(row.price_change_percent)}
          </span>
        ),
        sortValue: (row) => toNumber(row.price_change_percent)
      },
      {
        key: 'oi',
        header: 'OI',
        align: 'right',
        render: (row) => fmtOi(row.open_interest),
        sortValue: (row) => row.open_interest
      },
      {
        key: 'oi_change',
        header: 'OI %',
        align: 'right',
        render: (row) => (
          <span className={toneClass(row.oi_change_percent)}>
            {fmtPercent(row.oi_change_percent)}
          </span>
        ),
        sortValue: (row) => toNumber(row.oi_change_percent)
      },
      {
        key: 'state',
        header: 'Build-up',
        render: (row) => <span className={s.state}>{stateLabel(row.state)}</span>,
        sortValue: (row) => row.state
      },
      {
        key: 'lot',
        header: 'Lot',
        align: 'right',
        render: (row) => (row.lot_size === null ? '—' : String(row.lot_size)),
        sortValue: (row) => row.lot_size
      }
    ],
    []
  );

  if (loading) return <p className={s.panelEmpty}>Loading the board…</p>;

  return (
    <DataTable
      rows={rows}
      columns={columns}
      rowKey={(row) => row.symbol}
      defaultSort="price_change"
      empty="No contracts priced."
    />
  );
}

/** The up/down class for a signed value, or nothing when there is no value.
 *  Returned as `undefined` rather than `false` so it can be used both bare on
 *  `className` and inside `cx(...)`, which treats undefined as absent. */
function toneClass(value: string | null): string | undefined {
  const tone = direction(value);
  if (tone === 'up') return s.up;
  if (tone === 'down') return s.down;
  return undefined;
}
