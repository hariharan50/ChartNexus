import { cx } from '$shared/ui/cx';
import type { IndexKey } from '../dashboard-data';
import s from './IndexTabs.module.css';

interface Props {
  value: IndexKey;
  onChange?: ((key: IndexKey) => void) | undefined;
}

const tabs: { key: IndexKey; label: string }[] = [
  { key: 'NIFTY50', label: 'NIFTY 50' },
  { key: 'SENSEX', label: 'SENSEX' },
  { key: 'BANKNIFTY', label: 'BANK NIFTY' }
];

export default function IndexTabs({ value, onChange }: Props) {
  return (
    <div className={s.tabs} role="tablist" aria-label="Focused index">
      {tabs.map((tab) => (
        <button
          key={tab.key}
          type="button"
          role="tab"
          className={cx(s.tab, value === tab.key && s.active)}
          aria-selected={value === tab.key}
          onClick={() => onChange?.(tab.key)}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
