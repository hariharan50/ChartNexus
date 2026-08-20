import { cx } from '$shared/ui/cx';
import { timeLabel } from '../smart-oi-data';
import s from './ReplayBar.module.css';

/**
 * Playback controls for the replay sweep.
 *
 * The same control the Analyse workspace has, rebuilt here rather than
 * imported: its version is coupled to that page's `workspace` module, and the
 * CSS Module behind it cannot be extended across route directories anyway — the
 * convention the Options Lab pages already follow for their shared controls.
 *
 * `head` is an index into the **bar** axis. The route maps it onto the frame
 * axis by timestamp before handing it to the right-hand charts, because the two
 * axes have different cadences and sharing an index would sweep them apart.
 */
export const REPLAY_SPEEDS = [0.5, 1, 2, 4] as const;
export type ReplaySpeed = (typeof REPLAY_SPEEDS)[number];

interface Props {
  head: number;
  total: number;
  playing: boolean;
  speed: ReplaySpeed;
  /** ISO timestamp of the bar under the head, for the clock readout. */
  at: string | undefined;
  onHead: (head: number) => void;
  onPlaying: (playing: boolean) => void;
  onSpeed: (speed: ReplaySpeed) => void;
  onExit: () => void;
}

export default function ReplayBar({
  head,
  total,
  playing,
  speed,
  at,
  onHead,
  onPlaying,
  onSpeed,
  onExit
}: Props) {
  const atEnd = head >= total - 1;
  const max = Math.max(0, total - 1);

  return (
    <div className={s.bar} role="group" aria-label="Replay controls">
      <button
        type="button"
        className={s.btn}
        onClick={() => onHead(Math.max(0, head - 1))}
        disabled={head <= 0}
        title="Step back"
      >
        ‹
      </button>
      <button
        type="button"
        className={cx(s.btn, s.play)}
        onClick={() => (atEnd ? onHead(0) : onPlaying(!playing))}
        title={atEnd ? 'Restart' : playing ? 'Pause' : 'Play'}
      >
        {atEnd ? '↻' : playing ? '❚❚' : '►'}
      </button>
      <button
        type="button"
        className={s.btn}
        onClick={() => onHead(Math.min(max, head + 1))}
        disabled={atEnd}
        title="Step forward"
      >
        ›
      </button>

      <input
        type="range"
        className={s.scrub}
        min={0}
        max={max}
        value={Math.min(head, max)}
        onChange={(e) => onHead(Number(e.currentTarget.value))}
        aria-label="Replay position"
      />

      <span className={s.count}>
        {at ? timeLabel(at) : '—'}
        <span className={s.of}>
          {Math.min(head + 1, total)} / {total}
        </span>
      </span>

      <select
        className={s.speed}
        value={speed}
        onChange={(e) => onSpeed(Number(e.currentTarget.value) as ReplaySpeed)}
        aria-label="Replay speed"
      >
        {REPLAY_SPEEDS.map((option) => (
          <option key={option} value={option}>
            {option}×
          </option>
        ))}
      </select>

      <button type="button" className={cx(s.btn, s.exit)} onClick={onExit} title="Exit replay">
        Exit
      </button>
    </div>
  );
}
