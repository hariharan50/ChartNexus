import type { OvernightWindow, SessionBandRow } from '$contexts/global-markets/types';
import { cx } from '$shared/ui/cx';
import { STATE_LABELS, fmtDay, fmtIst, fmtPercent, intoLanes, tone } from '../gia-data';
import s from './HandoffTimeline.module.css';

interface Props {
  window: OvernightWindow;
  bands: SessionBandRow[];
}

/**
 * The overnight handoff, on one IST axis.
 *
 * The page's central idea made visible: a trading day passes around the globe
 * like a baton — Europe, then New York, then Asia at dawn — and lands on the
 * Indian open. Each band is a market's session at its true IST hours, tinted
 * by what that market did, so the story reads left to right without anyone
 * having to hold five timezones in their head.
 *
 * Hand-rolled rather than charted. This is a Gantt-shaped band layout, not a
 * series plot, and neither echarts nor lightweight-charts has a primitive for
 * it; CSS percentages off the server's 0–1 fractions are simpler than either
 * and do no date arithmetic on the client.
 */
export default function HandoffTimeline({ window, bands }: Props) {
  const lanes = intoLanes(bands);
  const ticks = axisTicks(window);

  return (
    <section className={s.wrap} aria-label="Overnight handoff timeline">
      <header className={s.head}>
        <div>
          <h2 className={s.title}>Overnight Handoff</h2>
          <p className={s.sub}>
            {fmtDay(window.opened_at)} {fmtIst(window.opened_at)} IST close →{' '}
            {fmtDay(window.closes_at)} {fmtIst(window.closes_at)} IST open
          </p>
        </div>
        <p className={s.legend}>
          <span className={cx(s.key, s.up)} /> higher
          <span className={cx(s.key, s.down)} /> lower
          <span className={cx(s.key, s.pending)} /> yet to open
        </p>
      </header>

      <div className={s.scroller}>
        <div className={s.plot}>
          {/* Hour gridlines, drawn behind the bands. */}
          <div className={s.grid} aria-hidden="true">
            {ticks.map((tick) => (
              <span
                className={s.gridline}
                key={tick.fraction}
                style={{ left: pct(tick.fraction) }}
              />
            ))}
          </div>

          {/* "Now" — the one marker that tells you where you are in the night. */}
          {window.progress > 0 && window.progress < 1 ? (
            <div className={s.now} style={{ left: pct(window.progress) }}>
              <span className={s.nowLabel}>now</span>
            </div>
          ) : null}

          <div className={s.lanes}>
            {lanes.map((lane) => (
              // A lane is identified by what starts it: the greedy packer is
              // deterministic, so the first band in a lane is a stable key.
              <div className={s.lane} key={lane[0]?.key ?? 'empty'}>
                {lane.map((band) => (
                  <div
                    className={cx(
                      s.band,
                      band.state === 'pending' && s.pending,
                      band.state === 'live' && s.live,
                      tone(band.change_percent) === 'up' && s.up,
                      tone(band.change_percent) === 'down' && s.down
                    )}
                    key={band.key}
                    style={{
                      left: pct(band.start_fraction),
                      width: pct(Math.max(band.end_fraction - band.start_fraction, 0.02))
                    }}
                    title={`${band.label} · ${fmtIst(band.opens_at)}–${fmtIst(band.closes_at)} IST · ${
                      STATE_LABELS[band.state]
                    }`}
                  >
                    <span className={s.bandLabel}>{band.label}</span>
                    <span className={cx(s.bandMove, 'cn-numeric')}>
                      {fmtPercent(band.change_percent)}
                    </span>
                  </div>
                ))}
              </div>
            ))}
          </div>

          <div className={s.axis} aria-hidden="true">
            {ticks.map((tick) => (
              <span className={s.tick} key={tick.fraction} style={{ left: pct(tick.fraction) }}>
                {tick.label}
              </span>
            ))}
          </div>
        </div>
      </div>

      <p className={s.foot}>
        Sessions are placed at their real IST hours, converted through each exchange&apos;s own
        timezone — so London and New York shift correctly across daylight saving.
      </p>
    </section>
  );
}

function pct(fraction: number): string {
  return `${(fraction * 100).toFixed(3)}%`;
}

/**
 * Three-hourly ticks across the window.
 *
 * Built from the window's own endpoints rather than from a fixed set, because
 * a Friday-evening window runs to Monday and is three times as long as an
 * ordinary one.
 */
function axisTicks(window: OvernightWindow): { fraction: number; label: string }[] {
  const start = new Date(window.opened_at).getTime();
  const end = new Date(window.closes_at).getTime();
  if (!Number.isFinite(start) || !Number.isFinite(end) || end <= start) return [];

  const span = end - start;
  const stepHours = span > 30 * 3600_000 ? 12 : 3;
  const step = stepHours * 3600_000;

  const ticks: { fraction: number; label: string }[] = [];
  for (let at = start; at <= end; at += step) {
    ticks.push({
      fraction: (at - start) / span,
      label: fmtIst(new Date(at).toISOString())
    });
  }
  return ticks;
}
