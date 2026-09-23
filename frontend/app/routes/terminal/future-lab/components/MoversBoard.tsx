import { useCallback, useDeferredValue, useMemo, useState } from 'react';
import { BOARD_REFRESH_SECONDS, useFuturesBoardQuery } from '$contexts/futures-analytics/queries';
import type { FuturesRow } from '$contexts/futures-analytics/types';
import { useInstruments } from '$contexts/instrument-catalog/queries';
import DataSourceBadge from '$shared/ui/DataSourceBadge';
import { SessionStatus } from './SessionHeader';
import { boardCsv, csvFilename, sectorsIn } from '../stocks-data';
import BuildLegend from './BuildLegend';
import MoversHeatmap from './MoversHeatmap';
import MoversTable from './MoversTable';
import MoversToolbar, { type BoardView } from './MoversToolbar';
import SidePanels from './SidePanels';
import s from './MoversBoard.module.css';

/**
 * The Live Future Market Movers board.
 *
 * Shared rather than duplicated: Market Movers and Stocks are the same board
 * over different slices of the universe, and two copies of this much
 * interaction — search, four filters, a view toggle, an export, a legend that
 * doubles as a filter — would drift apart within a week.
 *
 * Prices are the selected contract's **futures** last-traded price, not cash,
 * and the percentages beside them are the day's move against that contract's
 * previous close. Open interest arrives separately, from the background sweep,
 * which is why a back month can price without classifying — the board says so
 * rather than showing an empty build-up column as a quiet market.
 */
interface Props {
  title: string;
  subtitle: string;
  /** Restrict to one half of the universe. Omit for every contract. */
  kind?: 'stock' | 'index';
  /** What a row is called in the counts — "stocks", "contracts". */
  noun: string;
  /** Prefix for the exported file. */
  exportName: string;
}

const EMPTY: FuturesRow[] = [];

export default function MoversBoard({ title, subtitle, kind, noun, exportName }: Props) {
  const [search, setSearch] = useState('');
  // Filtering a couple of hundred rows on every keystroke; deferring keeps the
  // input crisp while the table catches up.
  const deferredSearch = useDeferredValue(search);
  const [sector, setSector] = useState('');
  const [state, setState] = useState('');
  const [view, setView] = useState<BoardView>('table');
  // 0 is the near month — the contract almost every reader means by "futures",
  // and the only one with a full open-interest sweep behind it.
  const [series, setSeries] = useState(0);

  const board = useFuturesBoardQuery({ ...(kind ? { kind } : {}), series });
  const { instruments } = useInstruments(kind ? { kind } : {});

  const wanted = useMemo(() => new Set(instruments.map((entry) => entry.symbol)), [instruments]);

  /** Every row in scope, before this page's own filters. */
  const allRows = useMemo(() => {
    const rows = board.data?.rows ?? EMPTY;
    if (rows.length === 0 || !kind) return rows;

    // Narrow here as well as in the request. The `kind` filter is an
    // optimisation the server may not apply — an older build ignores the
    // unknown parameter and returns the whole universe — so filter on what
    // actually arrived rather than trusting the request to have worked.
    const byKind = rows.filter((row) => row.kind === kind);
    if (byKind.length > 0) return byKind;
    // Response predates the `kind` field: fall back to the catalog.
    if (wanted.size === 0) return rows;
    return rows.filter((row) => wanted.has(row.symbol));
  }, [board.data, kind, wanted]);

  const sectors = useMemo(() => sectorsIn(allRows), [allRows]);

  const visible = useMemo(() => {
    const needle = deferredSearch.trim().toLowerCase();
    return allRows.filter((row) => {
      if (sector && row.sector !== sector) return false;
      if (state && row.state !== state) return false;
      if (!needle) return true;
      return (
        row.symbol.toLowerCase().includes(needle) || (row.name ?? '').toLowerCase().includes(needle)
      );
    });
  }, [allRows, deferredSearch, sector, state]);

  const onExport = useCallback(() => {
    const blob = new Blob([boardCsv(visible)], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = csvFilename(exportName);
    link.click();
    URL.revokeObjectURL(url);
  }, [visible, exportName]);

  const filtered = visible.length !== allRows.length;

  return (
    <div className={s.page}>
      <header className={s.header}>
        <div>
          <h1 className={s.title}>{title}</h1>
          <p className={s.subtitle}>{subtitle}</p>
        </div>
        <div className={s.status}>
          {/* The badge is the only thing separating a generated board from a
              real one; never label mock data "live". */}
          {board.data?.source ? <DataSourceBadge source={board.data.source} /> : null}
          {/* Replaces a bare "Updating…", which said a request was in flight
              and nothing about whether the board on screen was current. */}
          <SessionStatus
            intervalSeconds={BOARD_REFRESH_SECONDS}
            active={!board.isFetching}
            updatedAt={board.dataUpdatedAt}
          />
        </div>
      </header>

      <MoversToolbar
        search={search}
        onSearch={setSearch}
        series={series}
        onSeries={setSeries}
        expiry={board.data?.expiry}
        hasOpenInterest={board.data?.has_open_interest}
        sector={sector}
        sectors={sectors}
        onSector={setSector}
        state={state}
        onState={setState}
        view={view}
        onView={setView}
        onExport={onExport}
        exportDisabled={visible.length === 0}
      />

      {/* Counts describe the whole board, not the filtered view — otherwise
          selecting a state would show that state as 100% of the market. */}
      <div className={s.legendRow}>
        <BuildLegend
          rows={allRows}
          active={state || null}
          onPick={(next) => setState(next ?? '')}
        />
        <span className={s.count}>
          {filtered ? `${visible.length} of ${allRows.length}` : `${allRows.length}`} {noun}
          {board.data && board.data.covered < board.data.universe ? (
            <span className={s.partial}> · partial board</span>
          ) : null}
        </span>
      </div>

      {board.isError ? (
        <p className={s.error}>
          The board could not be loaded.
          {board.error instanceof Error ? (
            <span className={s.detail}> {board.error.message}</span>
          ) : null}
        </p>
      ) : board.data === undefined ? (
        // Distinct from an empty board: conflating them is what once made a
        // failed request read as "nothing priced".
        <p className={s.placeholder}>Loading the board…</p>
      ) : (
        <div className={s.body}>
          <div className={s.main}>
            {view === 'table' ? (
              <MoversTable
                rows={visible}
                emptyMessage={filtered ? 'No contracts match these filters.' : 'Nothing priced.'}
              />
            ) : (
              <MoversHeatmap rows={visible} />
            )}
          </div>
          <SidePanels
            rows={allRows}
            instruments={instruments}
            sector={sector}
            onSector={setSector}
          />
        </div>
      )}
    </div>
  );
}
