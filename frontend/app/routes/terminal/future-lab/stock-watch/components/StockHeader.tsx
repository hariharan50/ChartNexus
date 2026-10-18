import { useState } from 'react';
import type { Instrument } from '$contexts/instrument-catalog/types';
import type { DataSourceName, FuturesQuote, Quote } from '$contexts/broker-connections/types';
import DataSourceBadge from '$shared/ui/DataSourceBadge';
import Select from '$shared/ui/Select';
import SymbolPicker from '$shared/ui/SymbolPicker';
import { cx } from '$shared/ui/cx';
import {
  EMPTY,
  fmtAge,
  fmtDate,
  fmtIndian,
  fmtIst,
  fmtPercent,
  fmtPrice,
  fmtSigned,
  type FeedState,
  tone,
  wire
} from '../calc/format';
import s from '../stock-watch.module.css';

interface Props {
  symbol: string;
  instrument?: Instrument | undefined;
  instruments: Instrument[];
  catalogLoading: boolean;
  onSymbol: (symbol: string) => void;

  spot?: Quote | undefined;
  futures?: FuturesQuote | undefined;
  marketOpen: boolean;
  sessionDate?: string | undefined;
  feed: FeedState;

  expiries: string[];
  expiry: string | undefined;
  onExpiry: (expiry: string) => void;
  futuresExpiry?: string | undefined;

  watched: boolean;
  onToggleWatch: () => void;
}

/**
 * Who we are looking at, what it is doing, and how much to trust the numbers.
 *
 * The feed state sits in the header rather than in a corner because it
 * qualifies everything below it. A terminal whose staleness indicator is three
 * scrolls away from the price is a terminal that will get someone filled off a
 * four-minute-old quote.
 */
export default function StockHeader({
  symbol,
  instrument,
  instruments,
  catalogLoading,
  onSymbol,
  spot,
  futures,
  marketOpen,
  sessionDate,
  feed,
  expiries,
  expiry,
  onExpiry,
  futuresExpiry,
  watched,
  onToggleWatch
}: Props) {
  const [picking, setPicking] = useState(false);

  const price = wire(spot?.price);
  const change = wire(spot?.change);
  const changePercent = wire(spot?.change_percent);
  const open = wire(spot?.day_open);
  const previousClose = wire(spot?.previous_close);
  const direction = tone(changePercent ?? change);

  return (
    <header className={s.header}>
      <div className={s.stack} style={{ gap: 'var(--cn-space-2)' }}>
        <div className={s.identity}>
          <button
            type="button"
            className={s.symbolButton}
            onClick={() => setPicking(true)}
            aria-haspopup="dialog"
          >
            {symbol}
            <span className={s.muted} aria-hidden="true">
              ▾
            </span>
          </button>
          <div style={{ minWidth: 0 }}>
            <p className={s.company}>{instrument?.name ?? symbol}</p>
            <p className={s.companyMeta}>
              {instrument?.exchange ?? 'NSE'}
              {instrument?.sector ? ` · ${instrument.sector}` : ''}
              {instrument?.lot_size ? ` · Lot ${instrument.lot_size}` : ' · Lot size unknown'}
            </p>
          </div>
          <button
            type="button"
            className={cx(s.action, watched && s.actionPrimary)}
            onClick={onToggleWatch}
            aria-pressed={watched}
          >
            {watched ? 'Watching' : 'Watch'}
          </button>
        </div>

        <div className={s.quoteBlock}>
          <p className={cx(s.quotePrice, 'cn-numeric')}>{fmtPrice(price)}</p>
          <p className={cx(s.quoteChange, direction ? s[direction] : s.flat, 'cn-numeric')}>
            {fmtSigned(change)} ({fmtPercent(changePercent)})
          </p>
        </div>

        <div className={s.ohlc}>
          <span>
            Open <strong className="cn-numeric">{fmtPrice(open)}</strong>
          </span>
          <span>
            Prev close <strong className="cn-numeric">{fmtPrice(previousClose)}</strong>
          </span>
          {/* High, low and traded volume are not on the spot contract. Saying
              so beats printing the day's range off candle bars that may be on
              a different interval from the one the reader is looking at —
              the chart panel owns those and labels its timeframe. */}
          <span className={s.muted}>High / low / volume — see chart</span>
          {sessionDate ? <span>Session {fmtDate(sessionDate)}</span> : null}
        </div>
      </div>

      <div className={s.stack} style={{ gap: 'var(--cn-space-2)', alignItems: 'flex-end' }}>
        <div className={s.controls}>
          <div className={s.controlGroup}>
            <span className={s.controlLabel}>Options expiry</span>
            <Select
              value={expiry ?? ''}
              options={expiries.map((value) => ({ value, label: fmtDate(value) }))}
              onChange={onExpiry}
              ariaLabel="Options expiry"
              placeholder={expiries.length ? 'Select expiry' : 'No expiries'}
              size="sm"
              disabled={expiries.length === 0}
              align="right"
            />
          </div>
          <div className={s.controlGroup}>
            <span className={s.controlLabel}>Futures expiry</span>
            <p className={cx(s.tileValue, 'cn-numeric')} style={{ fontSize: 'var(--cn-text-sm)' }}>
              {futuresExpiry ? fmtDate(futuresExpiry) : EMPTY}
            </p>
          </div>
        </div>

        <div className={s.controls}>
          <span className={cx(s.chip, marketOpen ? s.chipUp : s.chipNeutral)}>
            {marketOpen ? 'Market open' : 'Market closed'}
          </span>
          <DataSourceBadge source={feed.source} ageSeconds={feed.ageSeconds} compact />
          <span className={s.muted} style={{ fontSize: 'var(--cn-text-xs)' }}>
            Updated {fmtIst(spot?.provenance.fetched_at)} IST · {fmtAge(feed.ageSeconds)}
          </span>
        </div>

        {futures ? (
          <p className={s.companyMeta}>
            Futures {futures.contract} ·{' '}
            <span className="cn-numeric">{fmtPrice(wire(futures.price))}</span> · vol{' '}
            <span className="cn-numeric">{fmtIndian(futures.volume)}</span>
          </p>
        ) : null}
      </div>

      {picking ? (
        <SymbolPicker
          instruments={instruments}
          selected={symbol}
          loading={catalogLoading}
          onPick={(next) => {
            onSymbol(next);
            setPicking(false);
          }}
          onClose={() => setPicking(false)}
        />
      ) : null}
    </header>
  );
}

/** The one-line banner shown whenever the data is not live and fresh. */
export function FeedNotice({ feed, source }: { feed: FeedState; source: DataSourceName }) {
  if (feed.freshness === 'fresh') return null;
  const severe = feed.freshness === 'very_stale' || feed.freshness === 'unavailable';
  return (
    <p
      className={cx(s.notice, severe ? s.noticeDanger : s.noticeWarn)}
      role={severe ? 'alert' : 'status'}
    >
      <strong>{source === 'mock' ? 'Simulated data' : 'Data warning'}</strong>
      <span>{feed.message}</span>
    </p>
  );
}
