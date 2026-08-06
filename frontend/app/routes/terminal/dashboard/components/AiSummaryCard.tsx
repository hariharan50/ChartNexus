import { Fragment } from 'react';
import { formatPrice } from '$shared/formatting/numbers';
import { cx } from '$shared/ui/cx';
import IconBrain from '$shared/ui/icons/IconBrain';
import type { AiSummary } from '../dashboard-data';
import s from './AiSummaryCard.module.css';
import Panel from './Panel';

interface Props {
  summary: AiSummary;
}

export default function AiSummaryCard({ summary }: Props) {
  const vixNote =
    summary.vix === undefined
      ? ''
      : summary.vix < 15
        ? 'VIX within normal range'
        : summary.vix < 20
          ? 'VIX slightly elevated'
          : 'VIX elevated — expect wider swings';

  // Assembled as one string rather than inline JSX: the Svelte template relied
  // on the browser collapsing its newlines into single spaces, and JSX's own
  // whitespace rules are different enough to shift the sentence.
  const tail =
    (summary.vix !== undefined ? `India VIX at ${summary.vix.toFixed(1)} — ${vixNote}. ` : '') +
    `PCR at ${summary.pcr.toFixed(2)}. ` +
    `Support ${formatPrice(summary.support, 1)} | Resistance ${formatPrice(summary.resistance, 1)}.`;

  return (
    <Panel accent title="AI Market Summary" icon={<IconBrain />}>
      <p className={s.summary}>
        {summary.biases.map((b, i) => (
          <Fragment key={b.label}>
            {b.label} AI bias:{' '}
            <strong className={cx(b.bias === 'Bullish' && s.bull, b.bias === 'Bearish' && s.bear)}>
              {b.bias}
            </strong>
            {b.confidence ? (
              <>
                {' '}
                <span className={s.conf}>({b.confidence}% confidence)</span>
              </>
            ) : null}
            .{i < summary.biases.length - 1 ? ' ' : ''}
          </Fragment>
        ))}{' '}
        {tail}
      </p>
    </Panel>
  );
}
