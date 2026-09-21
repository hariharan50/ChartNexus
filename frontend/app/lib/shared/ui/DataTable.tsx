import { useMemo, useState } from 'react';
import { cx } from './cx';
import s from './DataTable.module.css';

/**
 * A sortable table.
 *
 * Built because the terminal had no reusable table at all — the only one in the
 * tree was the Option Chain's, which is shaped around a two-sided CE/PE ladder
 * and cannot be borrowed. The Future Lab needs to render the whole F&O universe
 * in several places, so the sorting and the header semantics live here once.
 *
 * Not virtualized. The universe is ~220 rows, which the browser handles without
 * help; adding a windowing dependency for that would cost more than it saves.
 * If a view ever needs thousands of rows, that is the moment to revisit — not
 * before.
 */

export interface Column<T> {
  key: string;
  header: string;
  /** What to draw in the cell. */
  render: (row: T) => React.ReactNode;
  /**
   * The value to sort on. Omit to make the column unsortable — which is the
   * right choice for a column whose cell is a badge or an icon, where a sort
   * order would be arbitrary.
   */
  sortValue?: (row: T) => number | string | null;
  align?: 'left' | 'right' | undefined;
  /** A stable width, so numbers do not make columns jump as values change. */
  width?: string | undefined;
  /**
   * Class for the cell itself, not its contents. Needed where a column is
   * styled as a block — a build-up cell tinted edge to edge, say — which a
   * span inside the cell cannot do.
   */
  cellClassName?: string | undefined | ((row: T) => string | undefined);
  /**
   * Pin the column while the rest scrolls sideways. Only meaningful on the
   * first column; a dense board is unreadable once the symbol scrolls away.
   */
  sticky?: boolean | undefined;
}

type Direction = 'asc' | 'desc';

interface Props<T> {
  rows: T[];
  columns: Column<T>[];
  rowKey: (row: T) => string;
  /** Column key to sort by initially. */
  defaultSort?: string;
  defaultDirection?: Direction;
  empty?: string;
  caption?: string;
}

export default function DataTable<T>({
  rows,
  columns,
  rowKey,
  defaultSort,
  defaultDirection = 'desc',
  empty = 'Nothing to show.',
  caption
}: Props<T>) {
  const [sortKey, setSortKey] = useState<string | undefined>(defaultSort);
  const [direction, setDirection] = useState<Direction>(defaultDirection);

  const sorted = useMemo(() => {
    const column = columns.find((entry) => entry.key === sortKey);
    if (!column?.sortValue) return rows;

    const extract = column.sortValue;
    // Rows with no value sort to the bottom in both directions. A missing
    // number is missing, not zero, and parking it in the middle of the table
    // would read as a measurement that was never taken.
    const scored = rows.map((row) => ({ row, value: extract(row) }));
    const present = scored.filter((entry) => entry.value !== null && entry.value !== undefined);
    const absent = scored.filter((entry) => entry.value === null || entry.value === undefined);

    present.sort((a, b) => {
      const left = a.value as number | string;
      const right = b.value as number | string;
      if (typeof left === 'number' && typeof right === 'number') return left - right;
      return String(left).localeCompare(String(right));
    });
    if (direction === 'desc') present.reverse();

    return [...present, ...absent].map((entry) => entry.row);
  }, [rows, columns, sortKey, direction]);

  function toggle(column: Column<T>) {
    if (!column.sortValue) return;
    if (column.key === sortKey) {
      setDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'));
      return;
    }
    setSortKey(column.key);
    setDirection('desc');
  }

  if (rows.length === 0) {
    return <p className={s.empty}>{empty}</p>;
  }

  return (
    <div className={s.scroll}>
      <table className={s.table}>
        {caption ? <caption className={s.caption}>{caption}</caption> : null}
        <thead>
          <tr>
            {columns.map((column) => {
              const active = column.key === sortKey;
              const sortable = Boolean(column.sortValue);
              return (
                <th
                  key={column.key}
                  scope="col"
                  style={column.width ? { width: column.width } : undefined}
                  className={cx(column.align === 'right' && s.right, column.sticky && s.stickyHead)}
                  // Announced to assistive tech so the current order is not
                  // conveyed by the caret glyph alone.
                  aria-sort={
                    active ? (direction === 'asc' ? 'ascending' : 'descending') : undefined
                  }
                >
                  {sortable ? (
                    <button
                      type="button"
                      className={cx(s.sortBtn, active && s.sortActive)}
                      onClick={() => toggle(column)}
                    >
                      {column.header}
                      <span aria-hidden="true" className={s.caret}>
                        {active ? (direction === 'asc' ? '▲' : '▼') : '⇅'}
                      </span>
                    </button>
                  ) : (
                    column.header
                  )}
                </th>
              );
            })}
          </tr>
        </thead>
        <tbody>
          {sorted.map((row) => (
            <tr key={rowKey(row)}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={cx(
                    column.align === 'right' && s.right,
                    column.sticky && s.stickyCell,
                    typeof column.cellClassName === 'function'
                      ? column.cellClassName(row)
                      : column.cellClassName
                  )}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
