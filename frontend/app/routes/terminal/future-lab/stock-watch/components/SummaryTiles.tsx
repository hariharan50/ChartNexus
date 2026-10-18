import { cx } from '$shared/ui/cx';
import type { Basis } from '../calc/analytics';
import { EMPTY, fmtIndian, fmtPercent, fmtPrice, fmtSigned, tone } from '../calc/format';
import s from '../stock-watch.module.css';

export interface Tile {
  key: string;
  label: string;
  value: string;
  /** Colours the value. Omit where direction is meaningless — IV, PCR, ATR. */
  direction?: 'up' | 'down' | null | undefined;
  /** One line under the figure saying what it is or why it is missing. */
  note?: string | undefined;
  /** Marks the figure as model-derived rather than quoted. */
  modelled?: boolean | undefined;
}

/**
 * The six numbers a trader checks before reading anything else.
 *
 * Each tile either shows a figure or says why it cannot. A dash with an
 * explanation under it is more use than a zero — on PCR especially, where 0.00
 * is a real and very bearish reading, and "no put interest quoted" is not.
 */
export default function SummaryTiles({ tiles }: { tiles: Tile[] }) {
  return (
    <div className={s.tiles}>
      {tiles.map((tile) => (
        <div className={s.tile} key={tile.key}>
          <p className={s.tileKey}>
            {tile.label}
            {tile.modelled ? (
              <span
                className={cx(s.chip, s.chipAccent)}
                title="Computed here, not quoted by the feed"
              >
                Model
              </span>
            ) : null}
          </p>
          <p
            className={cx(
              s.tileValue,
              tile.direction ? s[tile.direction] : undefined,
              'cn-numeric'
            )}
          >
            {tile.value}
          </p>
          {tile.note ? <p className={s.tileNote}>{tile.note}</p> : null}
        </div>
      ))}
    </div>
  );
}

/** Build the standard tile set from what the page has loaded. */
export function summaryTiles(input: {
  futuresPrice?: number | undefined;
  futuresChangePercent?: number | undefined;
  basis?: Basis | undefined;
  atmIv?: number | undefined;
  ivQuoted: boolean;
  pcrOi?: number | undefined;
  callOi: number;
  putOi: number;
  atr?: number | undefined;
  atrTimeframe: string;
  spot?: number | undefined;
}): Tile[] {
  const {
    futuresPrice,
    futuresChangePercent,
    basis,
    atmIv,
    ivQuoted,
    pcrOi,
    callOi,
    putOi,
    atr,
    atrTimeframe,
    spot
  } = input;

  const basisTile: Tile = basis
    ? {
        key: 'basis',
        label: 'Futures basis',
        value: `${fmtSigned(basis.points)} (${fmtPercent(basis.percent)})`,
        direction: tone(basis.points),
        note:
          basis.state === 'premium'
            ? 'Futures above spot — the usual state, carrying cost of carry.'
            : basis.state === 'discount'
              ? 'Futures below spot. Worth checking against dividends and borrow.'
              : 'Futures level with spot.'
      }
    : {
        key: 'basis',
        label: 'Futures basis',
        value: EMPTY,
        note: 'Needs both a futures price and a spot price.'
      };

  return [
    {
      key: 'futures',
      label: 'Futures',
      value: fmtPrice(futuresPrice),
      direction: tone(futuresChangePercent),
      note:
        futuresChangePercent != null ? `${fmtPercent(futuresChangePercent)} on the day` : undefined
    },
    basisTile,
    {
      key: 'iv',
      label: 'ATM implied vol',
      value: atmIv != null ? `${atmIv.toFixed(2)}%` : EMPTY,
      modelled: atmIv != null && !ivQuoted,
      note:
        atmIv == null
          ? 'The chain carried no implied volatility for the at-the-money strikes.'
          : ivQuoted
            ? 'Mean of the ATM call and put, as quoted.'
            : 'Back-solved from the ATM premiums — not a quoted figure.'
    },
    {
      key: 'pcr',
      label: 'PCR (OI)',
      value: pcrOi != null ? pcrOi.toFixed(2) : EMPTY,
      note:
        pcrOi == null
          ? 'No call open interest to divide by.'
          : 'Put OI ÷ call OI across the chain. A ratio, not a direction.'
    },
    {
      key: 'oi',
      label: 'Chain open interest',
      value: `${fmtIndian(callOi)} C / ${fmtIndian(putOi)} P`,
      note: 'Totals across every quoted strike of this expiry.'
    },
    {
      key: 'atr',
      label: `ATR (14, ${atrTimeframe})`,
      value: atr != null ? fmtPrice(atr) : EMPTY,
      modelled: atr != null,
      note:
        atr == null
          ? 'Needs at least 15 bars on the selected timeframe.'
          : spot != null && spot > 0
            ? `${((atr / spot) * 100).toFixed(2)}% of spot — a typical bar's true range.`
            : "Wilder's true range, averaged over 14 bars."
    }
  ];
}
