import type { ComponentType } from 'react';
import { Link } from 'react-router';
import IconChart from '$shared/ui/icons/IconChart';
import IconMessage from '$shared/ui/icons/IconMessage';
import IconWallet from '$shared/ui/icons/IconWallet';
import s from './QuickActionsCard.module.css';
import Panel from './Panel';

interface Action {
  label: string;
  href: string;
  icon: ComponentType;
}

const actions: Action[] = [
  { label: 'Options Chain', href: '/option-chain', icon: IconChart },
  { label: 'Smart Money', href: '/smart-insights', icon: IconWallet },
  { label: 'Ask Copilot', href: '/copilot', icon: IconMessage }
];

export default function QuickActionsCard() {
  return (
    <Panel title="Quick Actions">
      <div className={s.actions}>
        {actions.map((action) => {
          const Icon = action.icon;
          return (
            // `/copilot` has no route — it is a .gitkeep-only directory in the
            // Svelte app too, so this link 404s there exactly as it does here.
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
