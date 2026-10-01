import { cx } from '$shared/ui/cx';
import Select from '$shared/ui/Select';
import IconReplay from '$shared/ui/icons/IconReplay';
import { REPLAY_SPEEDS, type ReplaySpeed } from '../workspace';
import s from './ReplayBar.module.css';

/**
 * Playback controls for replay mode: step through the loaded session bar by bar,
 * or let it play. The head is an index into the cell's candles; the parent slices
 * the data to it, so indicators and volume build up alongside the price.
 */
interface Props {
  head: number;
  total: number;
  playing: boolean;
  speed: ReplaySpeed;
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
        {Math.min(head + 1, total)} / {total}
      </span>

      <Select
        className={s.speed}
        size="sm"
        value={String(speed)}
        onChange={(next) => onSpeed(Number(next) as ReplaySpeed)}
        ariaLabel="Replay speed"
        options={REPLAY_SPEEDS.map((option) => ({
          value: String(option),
          label: `${option}×`
        }))}
      />

      <button type="button" className={cx(s.btn, s.exit)} onClick={onExit} title="Exit replay">
        <span className={s.ico}>
          <IconReplay />
        </span>
        Exit
      </button>
    </div>
  );
}
