import type { ComponentType } from 'react';
import { Link } from 'react-router';
import IconChart from '$shared/ui/icons/IconChart';
import IconMessage from '$shared/ui/icons/IconMessage';
import s from './QuickActionsCard.module.css';
import Panel from './Panel';

interface Action {
  label: string;
  href: string;
  icon: ComponentType;
}

const actions: Action[] = [
  { label: 'Options Chain', href: '/option-chain', icon: IconChart },
  { label: 'Advance Tools', href: '/advance-tool', icon: IconMessage }
];

export default function QuickActionsCard() {
  return (
    <Panel title="Quick Actions">
      <div className={s.actions}>
        {actions.map((action) => {
          const Icon = action.icon;
          return (
            <Link className={s.action} to={action.href} key={action.label}>
              <span className={s.ico} aria-hidden="true">
                <Icon />
              </span>
              {action.label}
            </Link>
          );
        })}
      </div>
    </Panel>
  );
}
