import { useEffect, useState } from 'react';
import Button from '$shared/ui/Button';
import { cx } from '$shared/ui/cx';
import {
  describeBand,
  EMPTY_OVERRIDES,
  overrideText,
  parseOverride,
  validateOverrides,
  type Overrides,
  type Settings
} from '../trade-buddy-data';
import s from './AlertSettings.module.css';

/**
 * The six thresholds, for the selected instrument.
 *
 * The design problem here is that the setting people need to tune and the
 * number they can feel are not the same thing. `0.06 x ATR` is the value that
 * transfers between indices — it is why a BANKNIFTY buffer is not a NIFTY
 * buffer — but nobody looks at a chart and thinks in ATR multiples. So every
 * row shows the resolved points beside the multiple, and the input accepts
 * points, because points are what you can check against a candle.
 *
 * A blank input means "use the scaled default", never zero. That distinction
 * is load-bearing: zero touch band would mean a level can never be touched.
 */
interface Props {
  settings: Settings | undefined;
  saving: boolean;
  onSave: (overrides: Overrides) => void;
}

interface Row {
  key: keyof Overrides;
  label: string;
  /** The resolved value currently in force, in points or seconds. */
  current: number;
  /** How the default is derived, for the hint under the input. */
  hint: string;
  unit: string;
  step: string;
}

export default function AlertSettings({ settings, saving, onSave }: Props) {
  const [draft, setDraft] = useState<Overrides>(EMPTY_OVERRIDES);
  const [dirty, setDirty] = useState(false);

  // Seed from the server, but never over a half-typed value.
  useEffect(() => {
    if (settings && !dirty) setDraft(settings.overrides);
  }, [settings, dirty]);

  if (!settings) return null;

  const { bands, defaults } = settings;
  const atr = bands.atr;

  const rows: Row[] = [
    {
      key: 'touch',
      label: 'Touch band',
      current: bands.touch,
      hint: describeBand(bands.touch, atr, defaults.fallback_touch),
      unit: 'pts',
      step: '0.5'
    },
    {
      key: 'approach',
      label: 'Approach band',
      current: bands.approach,
      hint: describeBand(bands.approach, atr, defaults.fallback_approach),
      unit: 'pts',
      step: '0.5'
    },
    {
      key: 'break_buffer',
      label: 'Break buffer',
      current: bands.break_buffer,
      hint: describeBand(bands.break_buffer, atr, defaults.fallback_break_buffer),
      unit: 'pts',
      step: '0.5'
    },
    {
      key: 'confirm_hold_seconds',
      label: 'Confirm hold',
      current: bands.confirm_hold_seconds,
      // Kept to one line like its neighbours: six hints of differing
      // height leave the row's baseline ragged. The reason a duration
      // does not scale is in the panel's own docs, not needed per field.
      hint: `Default ${defaults.confirm_hold_seconds}s · does not scale`,
      unit: 's',
      step: '1'
    },
    {
      key: 'cooldown_minutes',
      label: 'Cooldown',
      current: settings.cooldown_minutes,
      hint: `Default ${defaults.cooldown_minutes} min · 0 disables it`,
      unit: 'min',
      step: '1'
    },
    {
      key: 'daily_alert_cap',
      label: 'Daily cap',
      current: settings.daily_alert_cap,
      hint: `Default ${defaults.daily_alert_cap} · breaks ignore it`,
      unit: '/level',
      step: '1'
    }
  ];

  const problem = validateOverrides(draft);
  const overridden = rows.filter((row) => draft[row.key] !== null).length;

  function update(key: keyof Overrides, raw: string) {
    setDirty(true);
    setDraft((current) => ({ ...current, [key]: parseOverride(raw) }));
  }

  function reset() {
    setDirty(true);
    setDraft(EMPTY_OVERRIDES);
  }

  return (
    <section className={s.panel} aria-labelledby="tb-settings">
      <header className={s.head}>
        <h2 id="tb-settings" className={s.title}>
          Alert settings · <span className={s.symbol}>{settings.symbol}</span>
        </h2>
        <p className={s.note}>
          {atr !== null
            ? `Scaled from ATR(${defaults.atr_period}) = ${atr} for this index. Leave a field blank to keep the scaled value.`
            : 'ATR unavailable, so these are unscaled point defaults sized for NIFTY. Override them here until the feed recovers.'}
        </p>
      </header>

      <div className={s.rows}>
        {rows.map((row) => {
          const isOverridden = draft[row.key] !== null;
          return (
            <div key={row.key} className={s.row}>
              <label className={s.label} htmlFor={`tb-${row.key}`}>
                {row.label}
              </label>
              <div className={s.field}>
                <input
                  id={`tb-${row.key}`}
                  className={cx(s.input, isOverridden && s.inputOverridden)}
                  type="number"
                  inputMode="decimal"
                  step={row.step}
                  // The resolved value as the placeholder, so an empty field
                  // still shows what is actually in force.
                  placeholder={String(row.current)}
                  value={overrideText(draft[row.key])}
                  onChange={(event) => update(row.key, event.target.value)}
                />
                <span className={s.unit}>{row.unit}</span>
              </div>
              <p className={s.hint}>
                {row.hint}
                {isOverridden && <span className={s.overridden}> · overridden</span>}
              </p>
            </div>
          );
        })}
      </div>

      {problem && <p className={s.problem}>{problem}</p>}

      <div className={s.actions}>
        <Button onClick={() => onSave(draft)} loading={saving} disabled={!!problem}>
          Save settings
        </Button>
        <Button variant="ghost" onClick={reset} disabled={overridden === 0 && !dirty}>
          Reset to defaults
        </Button>
        <span className={s.count}>
          {overridden === 0
            ? 'All defaults'
            : `${overridden} override${overridden === 1 ? '' : 's'}`}
        </span>
      </div>

      <p className={s.note}>
        Saved settings apply to {settings.symbol} only. The running watcher picks them up on its
        next session.
      </p>
    </section>
  );
}
