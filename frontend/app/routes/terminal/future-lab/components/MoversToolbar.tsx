import { cx } from '$shared/ui/cx';
import Select from '$shared/ui/Select';
import IconSearch from '$shared/ui/icons/IconSearch';
import { STATES } from '../stocks-data';
import ExpiryPicker from './ExpiryPicker';
import s from './MoversToolbar.module.css';

export type BoardView = 'table' | 'heatmap';

interface Props {
  search: string;
  onSearch: (value: string) => void;
  /** Which contract series the board is showing: 0 near month, 1 next, 2 far. */
  series: number;
  onSeries: (series: number) => void;
  /** The expiry the board came back with, so the control cannot disagree with
   *  the rows beneath it. */
  expiry: string | null | undefined;
  /** Whether that board carries open interest. Undefined until it arrives. */
  hasOpenInterest: boolean | undefined;
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
  series,
  onSeries,
  expiry,
  hasOpenInterest,
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

      <div className={s.field}>
        <ExpiryPicker
          series={series}
          onSeries={onSeries}
          resolved={expiry}
          hasOpenInterest={hasOpenInterest}
        />
      </div>

      {/* Sectors come from a curated table; if none is loaded the filter would
          have a single option, so it is hidden rather than shown empty. */}
      {sectors.length > 0 ? (
        <div className={s.field}>
          <span className={s.caption}>Sector</span>
          <Select
            className={s.select}
            size="sm"
            value={sector}
            ariaLabel="Sector"
            onChange={onSector}
            options={[
              { value: '', label: 'All' },
              ...sectors.map((name) => ({ value: name, label: name }))
            ]}
          />
        </div>
      ) : null}

      <div className={s.field}>
        <span className={s.caption}>Filter</span>
        <Select
          className={s.select}
          size="sm"
          value={state}
          ariaLabel="Build-up filter"
          onChange={onState}
          options={[
            { value: '', label: 'All' },
            ...STATES.map((entry) => ({ value: entry.id, label: entry.label }))
          ]}
        />
      </div>

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
