import { useExpiriesQuery } from '$contexts/market-data/queries';
import { cx } from '$shared/ui/cx';
import Select from '$shared/ui/Select';
import s from './ExpiryPicker.module.css';

interface Props {
  /** The instrument whose expiries to list, e.g. `NIFTY`. */
  instrument: string;
  /** The chosen expiry, or `undefined` for "whatever the backend picks". */
  value: string | undefined;
  onChange: (expiry: string | undefined) => void;
  /**
   * What the payload actually resolved to. Shown against the default option so
   * the control names the real contract rather than the word "nearest".
   */
  resolved?: string | null | undefined;
  /**
   * Whether this page's data is a time series off the snapshot archive.
   *
   * The archive follows one expiry, so a far expiry on such a page has no
   * intraday history and drops to open-versus-now. Saying so under the control
   * is the difference between a documented limit and a chart that looks broken.
   */
  archiveBound?: boolean | undefined;
  /**
   * The tier the payload actually came back as.
   *
   * The note below is driven by this rather than inferred from the picked
   * date's position in the list. Those two disagree more often than you would
   * think - the archive stores whichever expiry the worker was following, which
   * after a settlement is no longer the first entry - and inferring it meant the
   * control stayed silent on exactly the degraded reads it existed to explain.
   */
  dataQuality?: string | undefined;
  /**
   * Hides the "Expiry" caption above the control.
   *
   * For a single row of controls — Option Greeks sits this next to four other
   * unlabelled selects, where one caption over one of them reads as a stray
   * heading rather than as a label. The `aria-label` on the select is
   * unaffected, so the control is still named for a screen reader.
   */
  hideLabel?: boolean | undefined;
  className?: string | undefined;
}

/**
 * The expiry control, shared by every Options Lab tool.
 *
 * It replaces what used to sit on these pages: a `<div>` that printed the
 * nearest expiry and could not be changed. Every tool showed the front month
 * and had no way to say so, which read as a broken dropdown rather than as a
 * missing feature.
 */
export default function ExpiryPicker({
  instrument,
  value,
  onChange,
  resolved,
  archiveBound = false,
  dataQuality,
  hideLabel = false,
  className
}: Props) {
  const query = useExpiriesQuery(instrument);
  const expiries = query.data?.expiries ?? [];

  // Only speak up once a specific expiry is picked, and only when the answer
  // that came back really was degraded.
  const degraded =
    archiveBound && value !== undefined && dataQuality !== undefined && dataQuality !== 'intraday';

  return (
    <div className={cx(s.wrap, className)}>
      {hideLabel ? null : <p className={s.label}>Expiry</p>}

      <Select
        className={s.control}
        ariaLabel="Expiry"
        value={value ?? ''}
        disabled={expiries.length === 0}
        onChange={(next) => onChange(next || undefined)}
        // The empty value means "whatever the backend picks", which is the
        // nearest expiry and the one every tool opens on.
        options={[
          { value: '', label: expiryLabel(resolved ?? null) },
          ...expiries.map((iso) => ({ value: iso, label: expiryLabel(iso) }))
        ]}
      />

      {query.isError ? (
        <p className={s.hint}>Couldn&apos;t load the expiry list — showing the nearest.</p>
      ) : degraded ? (
        <p className={s.hint}>
          The archive holds the nearest expiry only, so this one is shown as open-versus-now rather
          than through the session.
        </p>
      ) : null}
    </div>
  );
}

/**
 * `29 Sep 2026 (5d)` — the date and how long it has left.
 *
 * The day count is what makes the list readable: six dates in a dropdown are
 * hard to rank at a glance, and "(5d)" versus "(40d)" is the thing anyone
 * picking an expiry is actually choosing between.
 */
export function expiryLabel(iso: string | null): string {
  if (!iso) return 'Nearest expiry';
  const at = Date.parse(iso);
  if (Number.isNaN(at)) return iso;

  const days = Math.max(0, Math.ceil((at - Date.now()) / 86_400_000));
  const when = new Date(at);
  // IST, so an expiry never shifts a day for a reader west of the exchange.
  const parts = new Intl.DateTimeFormat('en-GB', {
    day: 'numeric',
    month: 'numeric',
    year: 'numeric',
    timeZone: 'Asia/Kolkata'
  }).formatToParts(when);
  const pick = (type: string) => parts.find((part) => part.type === type)?.value ?? '';

  const month = MONTHS[Number(pick('month')) - 1] ?? '';
  return `${Number(pick('day'))} ${month} ${pick('year')} (${days}d)`;
}

/**
 * Spelled out rather than taken from the locale.
 *
 * `Intl` with `month: 'short'` renders September as "Sept" under Node's ICU and
 * "Sep" under some browsers', so the same expiry would be labelled differently
 * depending on where the string was built — and the column would jitter by a
 * character between rows.
 */
const MONTHS = [
  'Jan',
  'Feb',
  'Mar',
  'Apr',
  'May',
  'Jun',
  'Jul',
  'Aug',
  'Sep',
  'Oct',
  'Nov',
  'Dec'
] as const;
