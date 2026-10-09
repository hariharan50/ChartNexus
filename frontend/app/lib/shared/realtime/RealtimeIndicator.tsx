import { cx } from '$shared/ui/cx';
import type { ConnectionState } from './client';
import s from './RealtimeIndicator.module.css';

/**
 * Whether the live stream is connected.
 *
 * **This is about the socket, not about the numbers.** `DataSourceBadge` is what
 * says where a figure came from; a green dot here only means events can arrive.
 * Keeping the two separate matters because they genuinely disagree: a connected
 * stream can be delivering simulated data, and a disconnected one leaves real
 * cached prices on screen that are perfectly good for another few seconds.
 *
 * Disconnected is not an error state. The pages still poll on their own
 * interval, so the only thing lost is immediacy — which is why nothing here is
 * red.
 */

interface Props {
  state: ConnectionState;
  /** Epoch ms of the last event, for the tooltip. */
  lastEventAt?: number | null | undefined;
  /** Hide the word, keep the dot — for a crowded header. */
  compact?: boolean | undefined;
}

const LABELS: Record<ConnectionState, string> = {
  idle: 'Offline',
  connecting: 'Connecting',
  open: 'Live',
  reconnecting: 'Reconnecting',
  offline: 'Offline'
};

const TITLES: Record<ConnectionState, string> = {
  idle: 'The live stream is not connected. Pages are updating on their timer.',
  connecting: 'Opening the live stream. Pages are updating on their timer.',
  open: 'Connected — updates arrive as the market moves.',
  reconnecting: 'The live stream dropped and is retrying. Pages are updating on their timer.',
  offline: 'The live stream is unavailable. Pages are updating on their timer.'
};

export default function RealtimeIndicator({ state, lastEventAt = null, compact = false }: Props) {
  const inFlight = state === 'connecting' || state === 'reconnecting';
  const title = lastEventAt
    ? `${TITLES[state]} Last update ${formatAge(Date.now() - lastEventAt)}.`
    : TITLES[state];

  return (
    <span
      className={cx(s.indicator, s[state])}
      title={title}
      // The label is the accessible name; a live region would announce every
      // reconnect of a flapping connection, which is noise, not information.
      role="status"
      aria-label={`Live stream: ${LABELS[state]}`}
    >
      <span className={cx(s.dot, inFlight && s.pulse)} aria-hidden="true" />
      {compact ? null : LABELS[state]}
    </span>
  );
}

function formatAge(ms: number): string {
  const seconds = Math.max(0, Math.round(ms / 1000));
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.round(seconds / 60)}m ago`;
  return `${Math.round(seconds / 3600)}h ago`;
}
