import type { SectionStatus } from '$contexts/pre-market/types';
import s from './SectionUnavailable.module.css';

interface Props {
  status: SectionStatus;
}

/**
 * What a panel shows when its upstream did not answer.
 *
 * The reason is rendered verbatim rather than replaced with a generic "no
 * data". "SENSEX has no constituent weight table" and "the option chain did
 * not answer (TimeoutError)" lead a reader to do completely different things —
 * one is permanent and one is worth a refresh — and a blank panel says
 * neither. This is why `SectionStatus` exists on the wire at all.
 */
export default function SectionUnavailable({ status }: Props) {
  if (status.availability === 'ok') return null;

  return (
    <p className={s.note} role="status">
      {status.reason ?? 'This panel has no data.'}
    </p>
  );
}
