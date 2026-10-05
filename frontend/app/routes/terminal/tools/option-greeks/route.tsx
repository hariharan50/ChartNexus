import { useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import EChart from '$shared/charts/EChart';
import { buildGreekLineOption } from '$shared/charts/options/greek-line';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import { lastTradingDayIST } from '$shared/formatting/ist-clock';
import { cx } from '$shared/ui/cx';
import DatePicker from '$shared/ui/DatePicker';
import Select from '$shared/ui/Select';
import ExpiryPicker from '../../options/components/ExpiryPicker';
import {
  bucketIndices,
  CALL_COLOR,
  DEFAULT_GREEK,
  DEFAULT_TIMEFRAME,
  formatGreek,
  formatPrice,
  getGreeks,
  GREEK_TABS,
  latestOf,
  legSeries,
  OI_INSTRUMENTS,
  pick,
  PUT_COLOR,
  qualityNote,
  REFETCH_MS,
  timeLabel,
  TIMEFRAMES,
  type GreekKey,
  type GreeksView,
  type Timeframe
} from './greeks-data';
import s from './route.module.css';
import type { Route } from './+types/route';

export const meta: Route.MetaFunction = () => [{ title: 'Option Greeks · Tools' }];

/**
 * Option Greeks — how one contract's IV and greeks moved through the session.
 *
 * Two panels rather than one chart with two lines: a call's delta and a put's
 * live on opposite sides of zero, and sharing a scale would flatten whichever
 * side is smaller. See `charts/options/greek-line.ts` for the rest of that
 * reasoning.
 *
 * The strike is pinned by the backend and named in both panel titles, so the
 * reader is always looking at one contract rather than at "whatever is at the
 * money right now".
 */
export default function OptionGreeks() {
  const [instIdx, setInstIdx] = useState(0);
  const [expiry, setExpiry] = useState<string | undefined>(undefined);
  const [timeframe, setTimeframe] = useState<Timeframe>(DEFAULT_TIMEFRAME);
  const [greek, setGreek] = useState<GreekKey>(DEFAULT_GREEK);
  const [live, setLive] = useState(true);
  const [date, setDate] = useState(lastTradingDayIST);

  const theme = useChartTheme();
  const instrument = OI_INSTRUMENTS[instIdx] ?? OI_INSTRUMENTS[0]!;
  const historyDate = live ? undefined : date;

  const query = useQuery<GreeksView>({
    queryKey: ['tools', 'greeks', instrument.symbol, expiry, historyDate],
    queryFn: () => getGreeks(instrument.symbol, { date: historyDate, expiry }),
    refetchInterval: live ? REFETCH_MS : false
  });

  const view = query.data;

  /** The two plotted lines, bucketed to the chosen interval. */
  const plot = useMemo(() => {
    if (!view || view.t.length === 0) return null;
    const keep = bucketIndices(view.t, timeframe);
    return {
      timestamps: pick(view.t, keep),
      ce: pick(legSeries(view.ce, greek), keep),
      pe: pick(legSeries(view.pe, greek), keep)
    };
  }, [view, timeframe, greek]);

  const tab = GREEK_TABS.find((entry) => entry.key === greek) ?? GREEK_TABS[0]!;
  const ceLatest = plot ? latestOf(plot.ce) : null;
  const peLatest = plot ? latestOf(plot.pe) : null;
  const headIv = { ce: view ? latestOf(view.ce.iv) : null, pe: view ? latestOf(view.pe.iv) : null };
  const underlying = view && view.underlying.length > 0 ? view.underlying.at(-1)! : view?.spot;

  const option = (values: (number | null)[], color: string, label: string) =>
    plot
      ? buildGreekLineOption(
          {
            label,
            color,
            timestamps: plot.timestamps,
            values,
            formatValue: (value) => formatGreek(greek, value),
            formatTime: timeLabel
          },
          theme
        )
      : null;

  const ceOption = plot ? option(plot.ce, CALL_COLOR, `CE ${tab.label}`) : null;
  const peOption = plot ? option(plot.pe, PUT_COLOR, `PE ${tab.label}`) : null;
  const note = qualityNote(view);

  return (
    <div className={s.page}>
      <header className={s.head}>
        <h1 className={s.title}>Option Greeks</h1>
      </header>

      {/* -- controls ------------------------------------------------------ */}
      <div className={s.controls}>
        {/* One option, and it is not a placeholder: the option chain this page
            reads is NFO's. Shown rather than hidden so the row names the
            instrument's full address. */}
        <Select
          className={s.field}
          value="NFO"
          ariaLabel="Exchange"
          disabled
          onChange={() => undefined}
          options={[{ value: 'NFO', label: 'NFO' }]}
        />

        <Select
          className={s.field}
          value={String(instIdx)}
          ariaLabel="Symbol"
          onChange={(next) => {
            setInstIdx(Number(next));
            // Expiries are per instrument; a NIFTY date means nothing on SENSEX.
            setExpiry(undefined);
          }}
          options={OI_INSTRUMENTS.map((entry, index) => ({
            value: String(index),
            label: entry.short
          }))}
        />

        <ExpiryPicker
          instrument={instrument.symbol}
          value={expiry}
          onChange={setExpiry}
          resolved={view?.expiry_date}
          archiveBound
          dataQuality={view?.data_quality}
          hideLabel
          className={s.expiry}
        />

        <Select
          className={s.field}
          value={timeframe}
          ariaLabel="Interval"
          onChange={setTimeframe}
          options={TIMEFRAMES.map((entry) => ({ value: entry.value, label: entry.label }))}
        />

        <Select
          className={s.field}
          value={live ? 'live' : 'historical'}
          ariaLabel="Session"
          onChange={(next) => setLive(next === 'live')}
          options={[
            { value: 'live', label: '1 Day · Live', hint: 'Today' },
            { value: 'historical', label: '1 Day · Archived', hint: 'Pick a day' }
          ]}
        />

        {live ? null : (
          <DatePicker
            value={date}
            max={lastTradingDayIST()}
            onChange={setDate}
            ariaLabel="Archived session"
          />
        )}

        <button
          type="button"
          className={s.refresh}
          onClick={() => void query.refetch()}
          disabled={query.isFetching}
        >
          {query.isFetching ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>

      {/* -- the contract under the cursor --------------------------------- */}
      <div className={s.context}>
        <span className={s.ctxItem}>
          ATM Strike: <b>{view?.strike != null ? formatPrice(view.strike) : '—'}</b>
        </span>
        <span className={s.ctxItem}>
          LTP: <b>{underlying != null ? formatPrice(underlying) : '—'}</b>
        </span>
        <span className={s.ctxItem}>
          <i className={cx(s.dot, s.callDot)} aria-hidden="true" />
          CE: <b>{view?.ce_symbol ?? '—'}</b>
          <span className={s.callText}>
            {headIv.ce != null ? formatGreek('iv', headIv.ce) : '—'}
          </span>
        </span>
        <span className={s.ctxItem}>
          <i className={cx(s.dot, s.putDot)} aria-hidden="true" />
          PE: <b>{view?.pe_symbol ?? '—'}</b>
          <span className={s.putText}>
            {headIv.pe != null ? formatGreek('iv', headIv.pe) : '—'}
          </span>
        </span>
      </div>

      {/* -- which greek --------------------------------------------------- */}
      <div className={s.tabs} role="tablist" aria-label="Greek">
        {GREEK_TABS.map((entry) => (
          <button
            key={entry.key}
            type="button"
            role="tab"
            aria-selected={greek === entry.key}
            className={cx(s.tab, greek === entry.key && s.tabActive)}
            onClick={() => setGreek(entry.key)}
          >
            {entry.label}
          </button>
        ))}
      </div>

      {query.isError ? (
        <div className={s.panelError} role="alert">
          <p>Couldn’t load the greeks for this contract.</p>
          <button type="button" onClick={() => void query.refetch()}>
            Retry
          </button>
        </div>
      ) : (
        <div className={s.charts}>
          <GreekPanel
            title={`${view?.ce_symbol ?? 'CE'} ${tab.label}`}
            value={ceLatest == null ? '—' : formatGreek(greek, ceLatest)}
            tone="call"
            option={ceOption}
            loading={query.isPending}
          />
          <GreekPanel
            title={`${view?.pe_symbol ?? 'PE'} ${tab.label}`}
            value={peLatest == null ? '—' : formatGreek(greek, peLatest)}
            tone="put"
            option={peOption}
            loading={query.isPending}
          />
        </div>
      )}

      <p className={s.note}>{tab.note}</p>
      {note ? <p className={s.quality}>{note}</p> : null}
      <p className={s.disclaimer}>
        Delta, gamma, theta and vega are derived here from each capture’s quoted implied volatility
        with Black-Scholes at a 7% risk-free rate — they are the exchange’s inputs, not the
        exchange’s numbers, and a broker’s own greeks will differ slightly. For educational and
        informational purposes only.
      </p>
    </div>
  );
}

interface PanelProps {
  title: string;
  value: string;
  tone: 'call' | 'put';
  option: ReturnType<typeof buildGreekLineOption> | null;
  loading: boolean;
}

function GreekPanel({ title, value, tone, option, loading }: PanelProps) {
  return (
    <section className={s.panel}>
      <header className={s.panelHead}>
        <h2 className={cx(s.panelTitle, tone === 'call' ? s.callText : s.putText)}>{title}</h2>
        <span className={cx(s.panelValue, 'cn-numeric')}>{value}</span>
      </header>
      {option ? (
        <EChart option={option} className={s.chart} />
      ) : (
        <p className={s.empty}>{loading ? 'Loading…' : 'No captures to draw for this session.'}</p>
      )}
    </section>
  );
}
