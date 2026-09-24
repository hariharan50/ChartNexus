import { Link } from 'react-router';
import type { FlowSummary } from '$contexts/market-breadth/types';
import { cx } from '$shared/ui/cx';
import IconBank from '$shared/ui/icons/IconBank';
import IconClock from '$shared/ui/icons/IconClock';
import {
  fmtGross,
  sessionLabel,
  streakLabel,
  toNumber
} from '../../future-lab/analysis/analysis-data';
import s from './FiiDiiCard.module.css';
import Panel from './Panel';

interface Props {
  /** The participant summary; absent until the flow query resolves. */
  summary?: FlowSummary | undefined;
  loading?: boolean;
}

interface Flow {
  label: string;
  /** Net cash in ₹ crore. `null` when the file carries no line for it. */
  net: number | null;
  streak: number;
  week: number | null;
}

/** The week window the backend aggregates over, so the footer can name it. */
const WEEK_SESSIONS = 5;

/**
 * Rupees crore, signed ahead of the symbol.
 *
 * `fmtCrore` puts the sign on the digits, which would read "₹+1,617 Cr" here.
 * The magnitude comes from the shared formatter either way, so this card and
 * the FII/DII page still round identically.
 */
function money(value: number): string {
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}₹${fmtGross(value)} Cr`;
}

/**
 * The day's cash-market participant flow, from the published NSE file.
 *
 * Only the **cash** segment appears here. The derivative segments the Analysis
 * page breaks out carry no DII line at all, so a two-column card showing them
 * would be half dashes; anyone who wants that detail follows the header link.
 */
export default function FiiDiiCard({ summary, loading = false }: Props) {
  const cash = summary?.segments.find((entry) => entry.segment === 'cash');

  const flows: Flow[] = [
    {
      label: 'FII Cash',
      net: toNumber(cash?.fii.net ?? null),
      streak: summary?.fii_cash_streak ?? 0,
      week: toNumber(summary?.fii_cash_week ?? null)
    },
    {
      label: 'DII Cash',
      net: toNumber(cash?.dii?.net ?? null),
      streak: summary?.dii_cash_streak ?? 0,
      week: toNumber(summary?.dii_cash_week ?? null)
    }
  ];

  // The backend totals five sessions, but only over what has actually been
  // published — naming a five-day window on a two-day archive overstates it.
  const windowSessions = Math.min(WEEK_SESSIONS, summary?.sessions ?? 0);

  return (
    <Panel
      title="FII / DII Flow"
      icon={<IconBank />}
      subtitle={summary ? sessionLabel(summary.session_date) : undefined}
      actions={
        <Link className={s.detail} to="/future-lab/fii-dii-summary">
          Detail
        </Link>
      }
    >
      <div className={s.grid}>
        {flows.map((flow) => (
          <div className={s.cell} key={flow.label}>
            <p className={s.label}>{flow.label}</p>

            {loading || flow.net === null ? (
              <span className={s.awaiting}>
                <span className={s.ico} aria-hidden="true">
                  <IconClock />
                </span>
                {loading ? 'Loading flow' : 'Not published'}
              </span>
            ) : (
              <>
                <p
                  className={cx(
                    s.value,
                    'mc-numeric',
                    flow.net > 0 && s.up,
                    flow.net < 0 && s.down
                  )}
                >
                  {money(flow.net)}
                </p>
                <p className={s.streak}>{streakLabel(flow.streak)}</p>
              </>
            )}
          </div>
        ))}
      </div>

      {summary && !loading && windowSessions > 0 ? (
        <p className={s.window}>
          Last {windowSessions} {windowSessions === 1 ? 'session' : 'sessions'} —{' '}
          <span className="mc-numeric">FII {money(flows[0]?.week ?? 0)}</span>,{' '}
          <span className="mc-numeric">DII {money(flows[1]?.week ?? 0)}</span>
        </p>
      ) : null}
    </Panel>
  );
}
