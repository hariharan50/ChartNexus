import { cx } from '$shared/ui/cx';
import { fmtDate } from '../calc/format';
import s from '../stock-watch.module.css';

interface Props {
  symbol: string;
  /** The options expiry on screen — the one date this page does know. */
  expiry?: string | undefined;
  futuresExpiry?: string | undefined;
  daysToExpiry: number;
}

/**
 * Corporate events, exchange restrictions and news — and why none are shown.
 *
 * **Nothing here is fabricated, which means almost nothing here is populated.**
 * This application has no corporate-actions feed, no NSE announcements client
 * and no licensed news provider wired in. The honest rendering of that is an
 * empty state naming exactly what is missing and what it would take to fill
 * it — not a plausible list of results dates and dividend announcements that a
 * reader would act on.
 *
 * The one thing this panel *can* say truthfully is the expiry arithmetic,
 * because those dates come from the broker's own contract master. Expiry is a
 * real event with real gamma and liquidity consequences, so it is surfaced
 * here rather than left implicit.
 *
 * **To make this panel real**, an integration needs: NSE corporate
 * announcements and the board-meeting calendar (results dates), the daily F&O
 * ban list and market-wide position-limit utilisation file, and a licensed
 * news source. Each wants its own provider adapter behind a port, the way
 * `global_markets` wraps NSE IX — and each must carry a source URL and a
 * publication timestamp, so a reader can check the claim rather than trust it.
 */
export default function EventsPanel({ symbol, expiry, futuresExpiry, daysToExpiry }: Props) {
  const expirySoon = daysToExpiry <= 3;

  return (
    <section className={s.panel}>
      <div className={s.panelHead}>
        <div>
          <h2 className={s.panelTitle}>Event intelligence</h2>
          <p className={s.panelSub}>Corporate actions, exchange restrictions and news</p>
        </div>
        <span className={cx(s.chip, s.chipWarn)}>No provider configured</span>
      </div>

      <div className={s.panelBody}>
        <div className={s.rows}>
          <div className={s.rowLine}>
            <dt>Options expiry</dt>
            <dd>
              {expiry ? fmtDate(expiry) : '—'}
              {expiry ? ` · ${daysToExpiry} day${daysToExpiry === 1 ? '' : 's'}` : ''}
            </dd>
          </div>
          <div className={s.rowLine}>
            <dt>Futures expiry</dt>
            <dd>{futuresExpiry ? fmtDate(futuresExpiry) : '—'}</dd>
          </div>
        </div>

        {expirySoon ? (
          <p className={cx(s.notice, s.noticeWarn)} style={{ marginTop: 'var(--cn-space-3)' }}>
            <span>
              <strong>Expiry is {daysToExpiry === 0 ? 'today' : `in ${daysToExpiry} days`}.</strong>{' '}
              Gamma rises sharply into expiry, so delta moves fast and a position that looked hedged
              this morning may not be this afternoon. Time value decays fastest here, and the book
              thins — spreads widen exactly when you most want to get out.
            </span>
          </p>
        ) : null}

        <p className={s.notice} style={{ marginTop: 'var(--cn-space-3)' }}>
          <span>
            <strong>No events are listed because none are available.</strong> This terminal has no
            corporate-actions feed, no NSE announcements client and no licensed news source wired
            in, so results dates, dividends, buybacks, mergers, the daily F&amp;O ban list and
            market-wide position-limit utilisation for {symbol} are all unknown here. They are not
            absent from the market — they are absent from this application, and the difference
            matters: check the exchange and your broker before holding anything through an
            announcement.
          </span>
        </p>

        <p className={s.notice} style={{ marginTop: 'var(--cn-space-2)' }}>
          <span>
            Wiring this up means one adapter per source behind a port — NSE corporate announcements
            and the board-meeting calendar, the daily ban list and MWPL file, and a licensed news
            provider — each carrying a source link and a publication timestamp, and each marking
            confirmed exchange disclosures apart from unverified reporting.
          </span>
        </p>
      </div>
    </section>
  );
}
