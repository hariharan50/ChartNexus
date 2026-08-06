import { useMemo, useState } from 'react';
import type { OptionChain } from '$contexts/broker-connections/types';
import { metrics, optionRows, toBackendSymbol } from '$contexts/market-data/derive';
import { useMarketStatusQuery, useOptionChainQuery } from '$contexts/market-data/queries';
import type { IndexKey } from '$contexts/market-data/view-models';
import { formatInt, formatPrice } from '$shared/formatting/numbers';
import { cx } from '$shared/ui/cx';
import DataSourceBadge from '$shared/ui/DataSourceBadge';
import IndexTabs from '../dashboard/components/IndexTabs';
import LiveBadge from '../dashboard/components/LiveBadge';
import OptionChainTable from './components/OptionChainTable';
import StatTile from './components/StatTile';
import s from './index.module.css';
import type { Route } from './+types/index';

export const meta: Route.MetaFunction = () => [{ title: 'Options Analytics · MarketCompass' }];

function n(value: string | null | undefined): number {
  return value == null ? Number.NaN : Number.parseFloat(value);
}

/** Volume-weighted put/call ratio; NaN when there is no call volume. */
function pcrByVolume(c: OptionChain): number {
  let ce = 0;
  let pe = 0;
  for (const strike of c.strikes) {
    ce += strike.ce?.volume ?? 0;
    pe += strike.pe?.volume ?? 0;
  }
  return ce > 0 ? pe / ce : Number.NaN;
}

/** A wide-band bias label for a PCR figure. */
function pcrLabel(pcr: number): string {
  if (Number.isNaN(pcr)) return '—';
  if (pcr >= 1.2) return 'Bullish';
  if (pcr <= 0.8) return 'Bearish';
  return 'Neutral';
}

export default function OptionsIndex() {
  const [focused, setFocused] = useState<IndexKey>('NIFTY50');

  const statusQ = useMarketStatusQuery();
  const chainQ = useOptionChainQuery(toBackendSymbol(focused));

  const chain = chainQ.data;
  const rows = useMemo(() => (chain ? optionRows(chain) : []), [chain]);
  const m = useMemo(() => (chain ? metrics(chain) : undefined), [chain]);
  const pcrVol = useMemo(() => (chain ? pcrByVolume(chain) : Number.NaN), [chain]);

  const provenance = chain?.provenance;
  const isLive = statusQ.data?.is_open ?? false;

  const writer = ((): { label: string; pill: string; tone: 'bullish' | 'bearish' | 'neutral' } => {
    switch (m?.writingPosture) {
      case 'PUT_WRITERS_DOMINANT':
        return { label: 'Put Writers', pill: 'Dominant', tone: 'bullish' };
      case 'CALL_WRITERS_DOMINANT':
        return { label: 'Call Writers', pill: 'Dominant', tone: 'bearish' };
      case 'BALANCED':
        return { label: 'Balanced', pill: 'Neutral', tone: 'neutral' };
      default:
        return { label: '—', pill: '', tone: 'neutral' };
    }
  })();

  const dash = (value: string) => (chain ? value : '—');

  return (
    <div className={s.page}>
      <header className={s.pageHead}>
        <div className={s.titles}>
          <h1>Options Analytics</h1>
          <p>Chain, PCR, max pain &amp; OI build-up</p>
        </div>
        <div className={s.controls}>
          <IndexTabs value={focused} onChange={setFocused} />
          {provenance ? (
            <DataSourceBadge source={provenance.source} ageSeconds={provenance.age_seconds} />
          ) : null}
          <LiveBadge live={isLive} />
        </div>
      </header>

      {/* Headline figures: one connected strip. */}
      <div className={s.summary}>
        <div className={s.cell}>
          <p className={s.sLabel}>Spot</p>
          <p className={cx(s.sValue, 'mc-numeric')}>{dash(formatPrice(n(chain?.spot_price)))}</p>
        </div>
        <div className={s.cell}>
          <p className={s.sLabel}>ATM</p>
          <p className={cx(s.sValue, 'mc-numeric')}>
            {chain?.atm_strike ? formatInt(n(chain.atm_strike)) : '—'}
          </p>
        </div>
        <div className={s.cell}>
          <p className={s.sLabel}>Call OI</p>
          <p className={cx(s.sValue, 'mc-numeric')}>{dash(formatInt(chain?.total_call_oi ?? 0))}</p>
        </div>
        <div className={s.cell}>
          <p className={s.sLabel}>Put OI</p>
          <p className={cx(s.sValue, 'mc-numeric')}>{dash(formatInt(chain?.total_put_oi ?? 0))}</p>
        </div>
      </div>

      {/* Derived metrics. */}
      <div className={s.metrics}>
        <StatTile
          label="PCR (OI)"
          value={m ? m.pcr.toFixed(2) : '—'}
          sub={m ? pcrLabel(m.pcr) : undefined}
        />
        <StatTile
          label="PCR (Vol)"
          value={Number.isNaN(pcrVol) ? '—' : pcrVol.toFixed(2)}
          sub={chain ? pcrLabel(pcrVol) : undefined}
        />
        <StatTile label="Max Pain" value={m ? formatInt(m.maxPain) : '—'} />
        <StatTile label="Support" value={m ? formatInt(m.support) : '—'} valueTone="bullish" />
        <StatTile
          label="Resistance"
          value={m ? formatInt(m.resistance) : '—'}
          valueTone="bearish"
        />
        <StatTile label="Writing" value={writer.label} pill={writer.pill} pillTone={writer.tone} />
      </div>

      {chainQ.isError ? (
        <div className={s.panelError} role="alert">
          <p>Couldn’t load the option chain.</p>
          <button type="button" onClick={() => void chainQ.refetch()}>
            Retry
          </button>
        </div>
      ) : (
        <OptionChainTable rows={rows} loading={chainQ.isPending} />
      )}

      <p className={s.disclaimer}>
        For educational and informational purposes only. MarketCompass is not a SEBI-registered
        investment adviser. Support, resistance, max pain and build-up labels are illustrative,
        derived from the live option chain, and may be delayed or inaccurate. Markets carry risk —
        consult a registered financial adviser before trading.
      </p>
    </div>
  );
}
