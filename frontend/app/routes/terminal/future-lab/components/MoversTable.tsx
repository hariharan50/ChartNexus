import { useMemo } from 'react';
import type { FuturesRow } from '$contexts/futures-analytics/types';
import DataTable, { type Column } from '$shared/ui/DataTable';
import SymbolAvatar from '$shared/ui/SymbolAvatar';
import { cx } from '$shared/ui/cx';
import { useTickFlash } from '$shared/ui/use-tick-flash';
import { direction, fmtCompact, fmtPercent, fmtPrice, stateMeta, toNumber } from '../stocks-data';
import s from './MoversTable.module.css';

/**
 * The board itself.
 *
 * Reuses the shared `DataTable` rather than growing a second table: its sorting
 * — including the rule that a null value sorts to the bottom rather than as
 * zero — is exactly what this needs, and Vol % is null for most rows on live
 * data.
 */
interface Props {
  rows: FuturesRow[];
  emptyMessage: string;
}

export default function MoversTable({ rows, emptyMessage }: Props) {
  const flashes = useTickFlash(
    rows,
    (row) => row.symbol,
    (row) => toNumber(row.price)
  );

  const columns: Column<FuturesRow>[] = useMemo(
    () => [
      {
        key: 'symbol',
        header: 'Symbol',
        sticky: true,
        width: '11rem',
        cellClassName: s.symbolCell,
        render: (row) => (
          <span className={s.symbolWrap} title={row.name ?? undefined}>
            <SymbolAvatar symbol={row.symbol} />
            <span className={s.symbol}>{row.symbol}</span>
          </span>
        ),
        sortValue: (row) => row.symbol
      },
      {
        key: 'sector',
        header: 'Sector',
        width: '9rem',
        render: (row) => <span className={s.sector}>{row.sector ?? '–'}</span>,
        sortValue: (row) => row.sector ?? ''
      },
      {
        key: 'openhl',
        header: 'Open HL',
        width: '6rem',
        render: (row) =>
          row.open_marker ? (
            <span
              className={cx(s.pill, row.open_marker === 'O=L' ? s.pillUp : s.pillDown)}
              // The badge is two letters; the meaning belongs in a title.
              title={
                row.open_marker === 'O=L'
                  ? 'Opened on the low — has not traded below its open'
                  : 'Opened on the high — has not traded above its open'
              }
            >
              {row.open_marker}
            </span>
          ) : (
            <span className={s.muted}>–</span>
          ),
        sortValue: (row) => row.open_marker ?? ''
      },
      {
        key: 'price',
        header: 'Price',
        align: 'right',
        width: '7rem',
        render: (row) => {
          const flash = flashes.get(row.symbol);
          return (
            <span
              className={cx(s.num, flash === 'up' && s.flashUp, flash === 'down' && s.flashDown)}
            >
              {fmtPrice(row.price)}
            </span>
          );
        },
        sortValue: (row) => toNumber(row.price)
      },
      {
        key: 'price_pct',
        header: 'Price %',
        align: 'right',
        width: '6.5rem',
        render: (row) => (
          <span className={cx(s.num, tone(row.price_change_percent))}>
            {fmtPercent(row.price_change_percent)}
          </span>
        ),
        sortValue: (row) => toNumber(row.price_change_percent)
      },
      {
        key: 'oi',
        header: 'OI',
        align: 'right',
        width: '6rem',
        render: (row) => <span className={s.num}>{fmtCompact(row.open_interest)}</span>,
        sortValue: (row) => row.open_interest
      },
      {
        key: 'oi_pct',
        header: 'OI %',
        align: 'right',
        width: '6.5rem',
        render: (row) => (
          <span className={cx(s.num, tone(row.oi_change_percent))}>
            {fmtPercent(row.oi_change_percent)}
          </span>
        ),
        sortValue: (row) => toNumber(row.oi_change_percent)
      },
      {
        key: 'build',
        header: 'Build',
        width: '7rem',
        // Tinted edge to edge, which is why the class goes on the cell rather
        // than on a span inside it.
        cellClassName: (row) => cx(s.buildCell, s[`build_${stateMeta(row.state).tone}`]),
        render: (row) => {
          const meta = stateMeta(row.state);
          return (
            <span className={s.build} title={meta.label}>
              <span aria-hidden="true">{meta.arrow}</span>
              <span>{meta.abbr}</span>
              <span className={s.srOnly}>{meta.label}</span>
            </span>
          );
        },
        sortValue: (row) => row.state
      },
      {
        key: 'volume',
        header: 'Volume',
        align: 'right',
        width: '6.5rem',
        render: (row) => <span className={s.num}>{fmtCompact(row.volume)}</span>,
        sortValue: (row) => row.volume
      },
      {
        key: 'vol_pct',
        header: 'Vol %',
        align: 'right',
        width: '6.5rem',
        render: (row) => (
          <span className={cx(s.num, tone(row.volume_change_percent))}>
            {fmtPercent(row.volume_change_percent)}
          </span>
        ),
        sortValue: (row) => toNumber(row.volume_change_percent)
      }
    ],
    [flashes]
  );

  return (
    <DataTable
      rows={rows}
      columns={columns}
      rowKey={(row) => row.symbol}
      defaultSort="price_pct"
      empty={emptyMessage}
    />
  );
}

function tone(value: string | null): string | undefined {
  const where = direction(value);
  if (where === 'up') return s.up;
  if (where === 'down') return s.down;
  return undefined;
}
