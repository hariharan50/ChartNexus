import { useMemo, useState } from 'react';
import EChart from '$shared/charts/EChart';
import {
  buildOpenInterestOption,
  type OiChartBar,
  type OiChartMode
} from '$shared/charts/options/open-interest';
import { useChartTheme } from '$shared/charts/theme/use-chart-theme';
import Select from '$shared/ui/Select';
import { cx } from '$shared/ui/cx';
import {
  type StrikeStat,
  buildupCandidates,
  maxPain,
  oiZones,
  sideStats,
  topAdditions,
  topOi,
  topReductions,
  totals
} from '../calc/analytics';
import { BUILDUP_LABEL, type EnrichedChain, atmIndex, windowAround } from '../calc/chain';
import { EMPTY, fmtIndian, fmtIndianSigned, fmtPercent, fmtPrice } from '../calc/format';
import s from '../stock-watch.module.css';

const MODES: { value: OiChartMode; label: string }[] = [
  { value: 'total', label: 'Open interest' },
  { value: 'change', label: 'Change in OI' },
  { value: 'change_total', label: 'OI with change' }
];

interface Props {
  chain: EnrichedChain;
}

/**
 * Where positioning sits across the ladder, and what moved today.
 *
 * The charts are facts. The *zones* below them are explicitly potential:
 * concentration of open interest at a strike tells you a lot of contracts are
 * open there and nothing at all about who holds them or why. The limitations
 * note is part of the panel rather than a footnote because the single most
 * common misreading of this screen — "the 2,600 call is resistance" — is
 * exactly the inference the data cannot support.
 */
export default function OiAnalytics({ chain }: Props) {
  const theme = useChartTheme();
  const [mode, setMode] = useState<OiChartMode>('total');
  const [span, setSpan] = useState('10');

  const visible = useMemo(() => {
    const centre = atmIndex(chain.rows, chain.spot, chain.atmStrike);
    return windowAround(chain.rows, centre, span === 'all' ? 'all' : Number(span));
  }, [chain, span]);

  const sums = useMemo(() => totals(chain.rows), [chain.rows]);
  const pain = useMemo(() => maxPain(chain.rows), [chain.rows]);
  const zones = useMemo(() => oiZones(chain.rows, chain.spot), [chain.rows, chain.spot]);
  const calls = useMemo(() => sideStats(visible, 'CE'), [visible]);
  const puts = useMemo(() => sideStats(visible, 'PE'), [visible]);
  const candidates = useMemo(() => buildupCandidates(chain.rows), [chain.rows]);

  const bars = useMemo<OiChartBar[]>(
    () =>
      visible.map((row) => ({
        strike: row.strike,
        callNow: row.ce?.oi ?? 0,
        putNow: row.pe?.oi ?? 0,
        // The chain quotes today's change, not the session-open level, so the
        // "open" series is reconstructed by subtraction. Correct for a leg
        // that traded yesterday and exactly wrong for one listed today — which
        // is why the chart offers a change-only mode that needs no such
        // reconstruction, and why that mode is the honest one on a new strike.
        callOpen: (row.ce?.oi ?? 0) - (row.ce?.oiChange ?? 0),
        putOpen: (row.pe?.oi ?? 0) - (row.pe?.oiChange ?? 0),
        callChg: row.ce?.oiChange ?? 0,
        putChg: row.pe?.oiChange ?? 0,
        atm: row.atm
      })),
    [visible]
  );

  const option = useMemo(
    () =>
      buildOpenInterestOption(
        {
          bars,
          mode,
          spot: chain.spot,
          maxPain: pain ?? 0,
          callColor: theme.call,
          putColor: theme.put,
          formatOi: (value) => fmtIndian(value),
          formatSigned: (value) => fmtIndianSigned(value),
          openLabel: 'Prev close',
          nowLabel: 'Now'
        },
        theme
      ),
    [bars, mode, chain.spot, pain, theme]
  );

  return (
    <div className={s.stack}>
      <section className={s.panel}>
        <div className={s.panelHead}>
          <div>
            <h2 className={s.panelTitle}>Open interest by strike</h2>
            <p className={s.panelSub}>
              {chain.expiry} · PCR(OI) {sums.pcrOi?.toFixed(2) ?? EMPTY} · PCR(vol){' '}
              {sums.pcrVolume?.toFixed(2) ?? EMPTY} · max pain{' '}
              {pain != null ? fmtPrice(pain) : EMPTY}
            </p>
          </div>
          <div className={s.panelActions}>
            <Select
              value={mode}
              options={MODES}
              onChange={setMode}
              ariaLabel="Chart mode"
              size="sm"
            />
            <Select
              value={span}
              options={[
                { value: '5', label: '±5' },
                { value: '10', label: '±10' },
                { value: '20', label: '±20' },
                { value: 'all', label: 'All' }
              ]}
              onChange={setSpan}
              ariaLabel="Strike range"
              size="sm"
              align="right"
            />
          </div>
        </div>
        <div className={s.panelBody}>
          {bars.length === 0 ? (
            <p className={s.empty}>No strikes to plot.</p>
          ) : (
            <EChart
              option={option}
              resetKey={`${chain.expiry}:${mode}:${span}`}
              className={s.chartBox}
              style={{ height: '18rem' }}
            />
          )}
        </div>
      </section>

      <div className={s.twoCol}>
        <StatTable title="Highest call OI" stats={topOi(calls)} />
        <StatTable title="Highest put OI" stats={topOi(puts)} />
        <StatTable title="Largest call OI additions" stats={topAdditions(calls)} showChange />
        <StatTable title="Largest put OI additions" stats={topAdditions(puts)} showChange />
        <StatTable title="Largest call OI reductions" stats={topReductions(calls)} showChange />
        <StatTable title="Largest put OI reductions" stats={topReductions(puts)} showChange />
      </div>

      <section className={s.panel}>
        <div className={s.panelHead}>
          <div>
            <h2 className={s.panelTitle}>Potential zones from OI concentration</h2>
            <p className={s.panelSub}>Strikes holding an outsized share of one side&apos;s book</p>
          </div>
        </div>
        <div className={s.panelBody}>
          {zones.length === 0 ? (
            <p className={s.empty}>
              No strike holds more than 8% of its side&apos;s open interest — positioning on this
              expiry is spread out rather than clustered.
            </p>
          ) : (
            <div className={s.tableScroll}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th className={s.left}>Strike</th>
                    <th className={s.left}>Reading</th>
                    <th>Open interest</th>
                    <th>Share of side</th>
                  </tr>
                </thead>
                <tbody>
                  {zones.map((zone) => (
                    <tr key={`${zone.strike}-${zone.kind}`}>
                      <td className={cx(s.left, 'cn-numeric')}>{fmtPrice(zone.strike)}</td>
                      <td className={s.left}>
                        <span
                          className={cx(
                            s.chip,
                            zone.kind === 'potential_resistance' ? s.chipDown : s.chipUp
                          )}
                        >
                          {zone.kind === 'potential_resistance'
                            ? 'Potential resistance'
                            : 'Potential support'}
                        </span>
                      </td>
                      <td>{fmtIndian(zone.oi)}</td>
                      <td>{zone.share.toFixed(1)}%</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <p className={s.notice} style={{ marginTop: 'var(--cn-space-3)' }}>
            <span>
              <strong>What open interest cannot tell you.</strong> A contract has a buyer and a
              seller, and the number counts the contract — not the direction either side took. A
              large call position at a strike is as consistent with a long holder writing covered
              calls, or a market maker hedging, as with a bearish bet. These are the levels where
              writers have an <em>incentive</em> to defend, which is not evidence that anyone will.
              Treat them as places to watch price behave, not as barriers.
            </span>
          </p>
        </div>
      </section>

      <section className={s.panel}>
        <div className={s.panelHead}>
          <div>
            <h2 className={s.panelTitle}>Build-up and unwinding</h2>
            <p className={s.panelSub}>
              Classified from each leg&apos;s own premium against its own open interest
            </p>
          </div>
        </div>
        <div className={s.panelBodyFlush}>
          {candidates.length === 0 ? (
            <p className={s.empty}>
              Nothing classified. Either both moves are inside the deadband on every strike, or the
              feed is not quoting per-leg price changes — in which case the chain&apos;s Build-up
              column reads <code>n/a</code> and this list stays empty rather than guessing from the
              underlying&apos;s direction.
            </p>
          ) : (
            <div className={s.tableScroll}>
              <table className={s.table}>
                <thead>
                  <tr>
                    <th className={s.left}>Contract</th>
                    <th className={s.left}>Pattern</th>
                    <th>Premium</th>
                    <th>Chg%</th>
                    <th>ΔOI</th>
                    <th>ΔOI%</th>
                    <th>Volume</th>
                    <th>IV</th>
                    <th className={s.left}>Rule that fired</th>
                  </tr>
                </thead>
                <tbody>
                  {candidates.map(({ strike, leg }) => (
                    <tr key={`${strike}-${leg.type}`}>
                      <td className={cx(s.left, 'cn-numeric')}>
                        {fmtPrice(strike)} {leg.type}
                      </td>
                      <td className={s.left}>
                        <span
                          className={cx(
                            s.chip,
                            leg.buildup.state === 'long_buildup' ||
                              leg.buildup.state === 'short_covering'
                              ? s.chipUp
                              : s.chipDown
                          )}
                        >
                          {BUILDUP_LABEL[leg.buildup.state]}
                        </span>
                      </td>
                      <td>{fmtPrice(leg.ltp)}</td>
                      <td>{fmtPercent(leg.changePercent)}</td>
                      <td>{fmtIndianSigned(leg.oiChange)}</td>
                      <td>{fmtPercent(leg.oiChangePercent)}</td>
                      <td>{fmtIndian(leg.volume)}</td>
                      <td>{leg.iv != null ? `${leg.iv.toFixed(1)}%` : EMPTY}</td>
                      <td className={cx(s.left, s.muted)} style={{ whiteSpace: 'normal' }}>
                        {leg.buildup.rule}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <p className={s.notice} style={{ margin: 'var(--cn-space-3)' }}>
            <span>
              Each row shows the two numbers that produced it rather than a confidence score. There
              is no validated statistical basis in this application for attaching a percentage to
              these patterns, so none is shown — the evidence is the figures, and a row whose volume
              is negligible beside its OI change deserves less weight than one whose is not.
            </span>
          </p>
        </div>
      </section>
    </div>
  );
}

function StatTable({
  title,
  stats,
  showChange = false
}: {
  title: string;
  stats: StrikeStat[];
  showChange?: boolean | undefined;
}) {
  return (
    <section className={s.panel}>
      <div className={s.panelHead}>
        <h2 className={s.panelTitle}>{title}</h2>
      </div>
      <div className={s.panelBodyFlush}>
        {stats.length === 0 ? (
          <p className={s.empty}>Nothing to rank.</p>
        ) : (
          <table className={s.table}>
            <thead>
              <tr>
                <th className={s.left}>Strike</th>
                <th>{showChange ? 'ΔOI' : 'OI'}</th>
                <th>{showChange ? 'ΔOI%' : 'Share'}</th>
                <th>Volume</th>
              </tr>
            </thead>
            <tbody>
              {stats.map((stat) => (
                <tr key={`${stat.strike}-${stat.type}`}>
                  <td className={cx(s.left, 'cn-numeric')}>{fmtPrice(stat.strike)}</td>
                  <td>{showChange ? fmtIndianSigned(stat.oiChange) : fmtIndian(stat.oi)}</td>
                  <td>
                    {showChange ? fmtPercent(stat.oiChangePercent) : `${stat.share.toFixed(1)}%`}
                  </td>
                  <td>{fmtIndian(stat.volume)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </section>
  );
}
