import type { RefObject } from 'react';
import Button from '$shared/ui/Button';
import { cx } from '$shared/ui/cx';
import LevelLadder from './LevelLadder';
import LevelTable from './LevelTable';
import {
  formatPrice,
  formatSessionDate,
  nearestLevel,
  stateLook,
  type DraftLevel,
  type ResolvedBands,
  type WatcherState
} from '../trade-buddy-data';
import s from './LevelsCard.module.css';

/**
 * One card for the levels: what they are, what price is doing to them, and
 * the fields that change them.
 *
 * It replaces two panels that were the same six prices twice — a form on the
 * left and a read-only live table on the right. Side by side they forced the
 * reader to match R1 in one against R1 in the other, and the page had no
 * single place that answered "where are we".
 *
 * Reading order is the order the question gets asked: is this today's set
 * (header) → where is price (LTP and the callout) → how far is the nearest
 * level (the map) → what is each level doing (the table) → change them
 * (footer). The LTP is the biggest thing on the card because it is what every
 * other number on it is relative to.
 */
interface Props {
  symbol: string;
  draft: readonly DraftLevel[];
  /** The saved marks, as a draft — what Discard restores and edits compare to. */
  saved: readonly DraftLevel[];
  live: readonly WatcherState[];
  price: number | null;
  bands: ResolvedBands | undefined;
  markedOn: string | null | undefined;
  /** Levels are current and being watched. */
  armed: boolean;
  stale: boolean;
  dailyCap: number;
  dirty: boolean;
  validation: string | null;
  saving: boolean;
  clearing: boolean;
  onChange: (index: number, price: string) => void;
  onSave: () => void;
  onDiscard: () => void;
  onClear: () => void;
  firstPriceRef: RefObject<HTMLInputElement | null>;
}

export default function LevelsCard({
  symbol,
  draft,
  saved,
  live,
  price,
  bands,
  markedOn,
  armed,
  stale,
  dailyCap,
  dirty,
  validation,
  saving,
  clearing,
  onChange,
  onSave,
  onDiscard,
  onClear,
  firstPriceRef
}: Props) {
  const nearest = nearestLevel(live, price);
  // The callout is for a level about to matter, not the nearest one on a quiet
  // day forty points away. Inside the approach band is exactly that threshold:
  // it is the distance at which the watcher itself starts speaking.
  const callout = nearest && bands && nearest.distance <= bands.approach ? nearest : null;
  // Nothing typed *and* nothing being watched. Both halves matter: the table
  // renders before either query resolves, and judging emptiness on the draft
  // alone would flash "No levels for NIFTY" on every single load — the one
  // message that must be trustworthy, since acting on it means marking levels
  // that are already marked.
  const empty = draft.every((row) => row.price.trim() === '') && live.length === 0;

  return (
    <section className={s.card} aria-labelledby="tb-levels">
      <header className={s.head}>
        <div className={s.headMain}>
          <h2 id="tb-levels" className={s.title}>
            Levels
          </h2>
          <p className={s.meta}>
            {symbol}
            {markedOn ? ` · marked ${formatSessionDate(markedOn)}` : ' · not marked yet'}
          </p>
          {armed && <span className={s.armed}>Armed for {formatSessionDate(markedOn)}</span>}
        </div>

        <div className={s.ltp}>
          <span className={s.ltpLabel}>LTP</span>
          <span className={cx(s.ltpValue, price === null && s.ltpMissing)}>
            {price === null ? '—' : formatPrice(price)}
          </span>
        </div>
      </header>

      {/* What to watch, in one line. Only when something is actually close:
          a permanent callout would be furniture, and furniture is ignored. */}
      {callout && (
        <p
          className={cx(
            s.callout,
            callout.level.role === 'support' ? s.calloutSupport : s.calloutResistance
          )}
        >
          <span className={s.calloutChip}>{callout.level.label}</span>
          <strong className={s.calloutState}>
            {stateLook(callout.level.state).label} {formatPrice(callout.level.level_price)}
          </strong>
          <span className={s.calloutDetail}>
            {callout.distance.toFixed(0)} pts away · touch at ±{bands?.touch}
          </span>
        </p>
      )}

      {empty ? (
        <div className={s.empty}>
          <svg className={s.emptyIcon} viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M3 8h18M3 16h18"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
            />
            <circle
              cx="9"
              cy="8"
              r="2.4"
              fill="var(--cn-bg)"
              stroke="currentColor"
              strokeWidth="1.6"
            />
            <circle
              cx="15"
              cy="16"
              r="2.4"
              fill="var(--cn-bg)"
              stroke="currentColor"
              strokeWidth="1.6"
            />
          </svg>
          <p className={s.emptyTitle}>No levels for {symbol}</p>
          <p className={s.emptyDetail}>
            Mark resistance and support for today and the watcher starts tracking {symbol} from
            09:15.
          </p>
          <Button variant="secondary" onClick={() => firstPriceRef.current?.focus()}>
            Mark today&apos;s levels
          </Button>
        </div>
      ) : (
        <LevelLadder levels={live} price={price} bands={bands} />
      )}

      <LevelTable
        draft={draft}
        saved={saved}
        live={live}
        price={price}
        dailyCap={dailyCap}
        stale={stale}
        onChange={onChange}
        firstPriceRef={firstPriceRef}
      />

      <footer className={s.foot}>
        <Button variant="ghost" onClick={onClear} loading={clearing} disabled={empty}>
          Clear all
        </Button>

        <div className={s.footRight}>
          <span className={cx(s.hint, validation && dirty && s.hintProblem)}>
            {validation && dirty
              ? validation
              : dirty
                ? 'Unsaved changes · saving resets live state'
                : 'All changes saved'}
          </span>
          <Button variant="secondary" onClick={onDiscard} disabled={!dirty}>
            Discard
          </Button>
          <Button onClick={onSave} loading={saving} disabled={!dirty || !!validation || clearing}>
            Save levels
          </Button>
        </div>
      </footer>
    </section>
  );
}
