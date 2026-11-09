import { useEffect, useState } from 'react';
import Button from '$shared/ui/Button';
import { cx } from '$shared/ui/cx';
import {
  describeBand,
  detectPreset,
  EMPTY_OVERRIDES,
  overrideText,
  parseOverride,
  presetOverrides,
  PRESET_COPY,
  validateOverrides,
  type BandPreset,
  type Overrides,
  type Settings
} from '../trade-buddy-data';
import s from './AlertSettings.module.css';

/** A half-width as a percentage of the diagram, clamped to fit the frame. */
function pct(halfWidth: number, span: number): number {
  if (!Number.isFinite(span) || span <= 0) return 0;
  return Math.min(100, (halfWidth / span) * 100);
}

/**
 * How close is close enough — the six thresholds, for the selected instrument.
 *
 * The design problem here is that the setting people need to tune and the
 * number they can feel are not the same thing. `0.06 x ATR` is the value that
 * transfers between indices — it is why a BANKNIFTY buffer is not a NIFTY
 * buffer — but nobody looks at a chart and thinks in ATR multiples. So every
 * row shows the resolved points beside the multiple, and the input accepts
 * points, because points are what you can check against a candle.
 *
 * A blank input means "use the scaled default", never zero. That distinction
 * is load-bearing: a zero touch band would mean a level can never be touched.
 *
 * The presets exist because six numbers is the wrong unit of decision. What
 * people actually want is "tell me earlier" or "stop pestering me", and
 * answering that by hand means editing three fields consistently and knowing
 * which direction is which. The buttons write the three band fields and leave
 * the throttles alone — a cooldown is a separate thought from a bandwidth.
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

const PRESETS: BandPreset[] = ['tight', 'default', 'wide', 'custom'];

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
      // Kept to one line like its neighbours: six hints of differing height
      // leave the row's baseline ragged. The reason a duration does not scale
      // is in the panel's own docs, not needed per field.
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
  const preset = detectPreset(settings, draft);
  // The diagram is drawn to the real numbers, not to fixed widths. Half a
  // width of headroom past the approach band, so the band that is supposed to
  // be the widest is visibly inside the frame rather than flush with it.
  const span = bands.approach * 1.6;

  function update(key: keyof Overrides, raw: string) {
    setDirty(true);
    setDraft((current) => ({ ...current, [key]: parseOverride(raw) }));
  }

  function choose(next: BandPreset) {
    // `custom` is a state the control can be *in*, never one you can pick:
    // there is nothing for it to write. Clicking it would either do nothing or
    // silently clear the numbers it is describing.
    if (next === 'custom') return;
    setDirty(true);
    setDraft((current) => ({ ...current, ...presetOverrides(settings as Settings, next) }));
  }

  function reset() {
    setDirty(true);
    setDraft(EMPTY_OVERRIDES);
  }

  return (
    <section className={s.card} aria-labelledby="tb-settings">
      <header className={s.head}>
        <h2 id="tb-settings" className={s.title}>
          Sensitivity
        </h2>
        <span className={cx(s.source, atr === null && s.sourceDegraded)}>
          {atr !== null ? `ATR(${defaults.atr_period}) scaled` : 'ATR offline · point defaults'}
        </span>
      </header>

      {/* Six numbers is the wrong unit of decision; "earlier" or "less often"
          is the real one. */}
      <div className={s.presets} role="radiogroup" aria-label="Alert sensitivity">
        {PRESETS.map((option) => (
          <button
            key={option}
            type="button"
            role="radio"
            aria-checked={preset === option}
            className={cx(s.preset, preset === option && s.presetActive)}
            // Custom is reachable only by editing a field, so it must not
            // look clickable when it is not the current state.
            disabled={option === 'custom' && preset !== 'custom'}
            title={PRESET_COPY[option].detail}
            onClick={() => choose(option)}
          >
            {PRESET_COPY[option].label}
          </button>
        ))}
      </div>
      <p className={s.presetNote}>{PRESET_COPY[preset].detail}</p>

      {/* What the three bands mean, drawn once. The numbers are in the fields
          below; this is only the shape — which band is inside which, and that
          a break has to hold. `aria-hidden` because the legend under it says
          the same thing in words. */}
      <div className={s.diagram} aria-hidden="true">
        <span className={s.approachZone} style={{ width: `${pct(bands.approach, span)}%` }} />
        <span className={s.touchZone} style={{ width: `${pct(bands.touch, span)}%` }} />
        <span className={s.levelLine} />
        <span
          className={s.breakLine}
          style={{ left: `${50 + pct(bands.break_buffer, span) / 2}%` }}
        />
        <span
          className={s.breakLine}
          style={{ left: `${50 - pct(bands.break_buffer, span) / 2}%` }}
        />
      </div>
      <p className={s.legend}>
        <span>Approach ±{bands.approach}</span>
        <span>Touch ±{bands.touch}</span>
        <span>
          Break past ±{bands.break_buffer} for {bands.confirm_hold_seconds}s
        </span>
      </p>

      <div className={s.grid}>
        {rows.map((row) => {
          const isOverridden = draft[row.key] !== null;
          return (
            <div key={row.key} className={s.field}>
              <label className={s.label} htmlFor={`tb-${row.key}`}>
                {row.label}
              </label>
              <div className={cx(s.inputBox, isOverridden && s.inputBoxOverridden)}>
                <input
                  id={`tb-${row.key}`}
                  className={s.input}
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
              {/* One line, clipped if long, with the full text on hover: six
                  hints of differing height leave the row of fields ragged,
                  and in a 24rem column the ATR form of a band does not fit.
                  The resolved points are also the field's placeholder, so the
                  number that matters is never the part that is cut. */}
              <p className={s.hint} title={row.hint}>
                {row.hint}
                {isOverridden && <span className={s.overridden}> · overridden</span>}
              </p>
            </div>
          );
        })}
      </div>

      {problem && <p className={s.problem}>{problem}</p>}

      <footer className={s.foot}>
        <span className={s.scope}>
          {settings.symbol} only · picked up next session ·{' '}
          {overridden === 0
            ? 'all defaults'
            : `${overridden} override${overridden === 1 ? '' : 's'}`}
        </span>
        <div className={s.actions}>
          <Button variant="ghost" onClick={reset} disabled={overridden === 0 && !dirty}>
            Reset to defaults
          </Button>
          <Button onClick={() => onSave(draft)} loading={saving} disabled={!!problem}>
            Save settings
          </Button>
        </div>
      </footer>
    </section>
  );
}
