import DataSourceBadge from '$shared/ui/DataSourceBadge';
import { cx } from '$shared/ui/cx';
import { INDICES, type IndexFixture } from '../../fixtures';
import s from './ChainWidget.module.css';

interface Props {
  selected: string;
  onSelect: (key: string) => void;
  fixture: IndexFixture;
}

/**
 * The option chain, as the terminal draws it.
 *
 * A live component rather than a screenshot: it stays correct when the design
 * system moves, weighs less than a PNG, and the CSP forbids remote images
 * anyway. The provenance badge is the real one, reading "Simulated" — the page
 * demonstrates the guarantee by holding itself to it.
 */
export default function ChainWidget({ selected, onSelect, fixture }: Props) {
  const ladderLabel = `${fixture.label} option chain`;

  return (
    <div className={s.widget}>
      <div className={s.head}>
        <div className={s.tabs} role="tablist" aria-label="Index">
          {INDICES.map((index) => (
            <button
              key={index.key}
              type="button"
              role="tab"
              aria-selected={index.key === selected}
              className={cx(s.tab, index.key === selected && s.tabOn)}
              onClick={() => onSelect(index.key)}
            >
              {index.label}
            </button>
          ))}
        </div>
        <DataSourceBadge source="mock" compact />
      </div>

      <div className={s.stats}>
        <Stat
          label="Spot"
          value={fmt(fixture.spot)}
          tone={fixture.changePercent >= 0 ? 'up' : 'down'}
        />
        <Stat label="PCR (OI)" value={fixture.pcr.toFixed(2)} />
        <Stat label="Max pain" value={fmt(fixture.maxPain)} />
        <Stat label="ATM" value={fmt(fixture.atm)} />
      </div>

      {/* Focusable and named: the ladder scrolls, and a scrollable region that
          cannot be reached by keyboard is unreachable content for anyone not
          using a mouse. The global :focus-visible outline makes it visible.

          The two linters disagree here — jsx-a11y objects to tabIndex on a
          non-interactive element, while axe's `scrollable-region-focusable`
          fails without it and names exactly this markup as the fix. The
          accessibility suite is the one measuring the real page, so it wins. */}
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex */}
      <div className={s.scroll} tabIndex={0} role="region" aria-label={ladderLabel}>
        <table className={s.table}>
          <caption className={s.caption}>
            Option chain around ATM for {fixture.label} — simulated data
          </caption>
          <thead>
            <tr>
              <th scope="col">Call OI</th>
              <th scope="col">LTP</th>
              <th scope="col" className={s.strikeCol}>
                Strike
              </th>
              <th scope="col">LTP</th>
              <th scope="col">Put OI</th>
            </tr>
          </thead>
          <tbody>
            {fixture.rows.map((row) => {
              const atm = row.strike === fixture.atm;
              return (
                <tr key={row.strike} className={cx(atm && s.atm)}>
                  <td>
                    <Bar value={row.ce.oi} max={fixture.maxOi} tone="call" />
                  </td>
                  <td className={cx(s.num, 'cn-numeric')}>{row.ce.ltp.toFixed(2)}</td>
                  <th scope="row" className={cx(s.strike, 'cn-numeric')}>
                    {fmt(row.strike)}
                    {row.strike === fixture.support ? <span className={s.tagUp}>S</span> : null}
                    {row.strike === fixture.resistance ? (
                      <span className={s.tagDown}>R</span>
                    ) : null}
                  </th>
                  <td className={cx(s.num, 'cn-numeric')}>{row.pe.ltp.toFixed(2)}</td>
                  <td>
                    <Bar value={row.pe.oi} max={fixture.maxOi} tone="put" />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'up' | 'down' }) {
  return (
    <div className={s.stat}>
      <span className={s.statLabel}>{label}</span>
      <span
        className={cx(s.statValue, 'cn-numeric', tone === 'up' && s.up, tone === 'down' && s.down)}
      >
        {value}
      </span>
    </div>
  );
}

function Bar({ value, max, tone }: { value: number; max: number; tone: 'call' | 'put' }) {
  const pct = Math.round((value / max) * 100);
  return (
    <span className={cx(s.bar, tone === 'call' ? s.barCall : s.barPut)}>
      <span className={s.barFill} style={{ width: `${pct}%` }} aria-hidden="true" />
      <span className={cx(s.barText, 'cn-numeric')}>{compact(value)}</span>
    </span>
  );
}

function fmt(value: number): string {
  return value.toLocaleString('en-IN', { maximumFractionDigits: 0 });
}

function compact(value: number): string {
  if (value >= 1e7) return `${(value / 1e7).toFixed(2)}Cr`;
  if (value >= 1e5) return `${(value / 1e5).toFixed(2)}L`;
  if (value >= 1e3) return `${(value / 1e3).toFixed(1)}K`;
  return String(value);
}
