import { cx } from '$shared/ui/cx';
import IconBank from '$shared/ui/icons/IconBank';
import IconClock from '$shared/ui/icons/IconClock';
import s from './FiiDiiCard.module.css';
import Panel from './Panel';

interface Flow {
  label: string;
  /** Net cash in ₹ crore. `null` until the data feed lands. */
  value: number | null;
}

interface Props {
  flows?: Flow[];
}

const DEFAULT_FLOWS: Flow[] = [
  { label: 'FII Cash', value: null },
  { label: 'DII Cash', value: null }
];

function formatCr(value: number): string {
  const sign = value > 0 ? '+' : value < 0 ? '−' : '';
  return `${sign}₹${Math.abs(value).toLocaleString('en-IN')} Cr`;
}

export default function FiiDiiCard({ flows = DEFAULT_FLOWS }: Props) {
  return (
    <Panel title="FII / DII Flow" icon={<IconBank />}>
      <div className={s.grid}>
        {flows.map((flow) => (
          <div className={s.cell} key={flow.label}>
            <p className={s.label}>{flow.label}</p>
            {flow.value === null ? (
              <span className={s.awaiting}>
                <span className={s.ico} aria-hidden="true">
                  <IconClock />
                </span>
                Awaiting market data
              </span>
            ) : (
              <p
                className={cx(
                  s.value,
                  'mc-numeric',
                  flow.value > 0 && s.up,
                  flow.value < 0 && s.down
                )}
              >
                {formatCr(flow.value)}
              </p>
            )}
          </div>
        ))}
      </div>
    </Panel>
  );
}
