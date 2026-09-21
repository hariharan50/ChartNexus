import { cx } from '$shared/ui/cx';
import IconSearch from '$shared/ui/icons/IconSearch';
import { STATES } from '../stocks-data';
import s from './MoversToolbar.module.css';

export type BoardView = 'table' | 'heatmap';

interface Props {
  search: string;
  onSearch: (value: string) => void;
  /** Front-month expiry, already formatted — e.g. "Sep (8d) Current". */
  expiryLabel: string;
  sector: string;
  sectors: string[];
  onSector: (value: string) => void;
  state: string;
  onState: (value: string) => void;
  view: BoardView;
  onView: (value: BoardView) => void;
  onExport: () => void;
  exportDisabled: boolean;
}

export default function MoversToolbar({
  search,
  onSearch,
  expiryLabel,
  sector,
  sectors,
  onSector,
  state,
  onState,
  view,
  onView,
  onExport,
  exportDisabled
}: Props) {
  return (
    <div className={s.toolbar}>
      <label className={s.field}>
        <span className={s.caption}>Search</span>
        <span className={s.searchBox}>
          <span className={s.searchIco} aria-hidden="true">
            <IconSearch />
          </span>
          <input
            className={s.search}
            type="search"
            value={search}
            placeholder="Search symbol"
            aria-label="Search symbol"
            onChange={(event) => onSearch(event.currentTarget.value)}
          />
        </span>
      </label>

      {/*
        A chip, not a dropdown. The board reads the front-month contract and
        nothing else, so a control offering other expiries would be a promise
        it cannot keep. Showing the real expiry and days remaining is the
        honest half of what the reference design implies.
      */}
      <div className={s.field}>
        <span className={s.caption}>Expiry</span>
        <span className={s.chip} title="The board tracks the front-month contract">
          {expiryLabel}
        </span>
      </div>

      {/* Sectors come from a curated table; if none is loaded the filter would
          have a single option, so it is hidden rather than shown empty. */}
      {sectors.length > 0 ? (
        <label className={s.field}>
          <span className={s.caption}>Sector</span>
          <select
            className={s.select}
            value={sector}
            aria-label="Sector"
            onChange={(event) => onSector(event.currentTarget.value)}
          >
            <option value="">All</option>
            {sectors.map((name) => (
              <option key={name} value={name}>
                {name}
              </option>
            ))}
          </select>
        </label>
      ) : null}

      <label className={s.field}>
        <span className={s.caption}>Filter</span>
        <select
          className={s.select}
          value={state}
          aria-label="Build-up filter"
          onChange={(event) => onState(event.currentTarget.value)}
        >
          <option value="">All</option>
          {STATES.map((entry) => (
            <option key={entry.id} value={entry.id}>
              {entry.label}
            </option>
          ))}
        </select>
      </label>

      <div className={s.right}>
        <div className={s.viewToggle} role="group" aria-label="View">
          <button
            type="button"
            className={cx(s.toggleBtn, view === 'table' && s.toggleOn)}
            aria-pressed={view === 'table'}
            onClick={() => onView('table')}
          >
            Table
          </button>
          <button
            type="button"
            className={cx(s.toggleBtn, view === 'heatmap' && s.toggleOn)}
            aria-pressed={view === 'heatmap'}
            onClick={() => onView('heatmap')}
          >
            Heatmap
          </button>
        </div>

        <button
          type="button"
          className={s.export}
          onClick={onExport}
          disabled={exportDisabled}
          title="Download the rows as shown"
        >
          <span aria-hidden="true">↓</span>
          <span className={s.srOnly}>Export CSV</span>
        </button>
      </div>
    </div>
  );
}
