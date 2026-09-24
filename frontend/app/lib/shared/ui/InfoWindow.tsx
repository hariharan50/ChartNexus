import { useEffect, useId, useState, type ReactNode } from 'react';
import { cx } from './cx';
import w from './InfoWindow.module.css';

export interface InfoTab {
  id: string;
  label: string;
  content: ReactNode;
}

interface Props {
  title: string;
  /** One line under the title saying what the window covers. */
  kicker?: string | undefined;
  /** A short badge beside the title — initials, a symbol, an emoji. */
  mark?: ReactNode;
  tabs: InfoTab[];
  onClose: () => void;
}

/**
 * A floating, dismissible explainer with a tab strip.
 *
 * Only chrome: the backdrop, Escape, the scroll lock, the tab strip and the
 * close button. What goes in each tab is the caller's, which is what lets one
 * window serve pages whose content has nothing in common.
 *
 * Lifted from `ai-console/components/AgentInfoWindow`, which solved all of this
 * first. That component's content is bound to the agent docs it renders, so the
 * shell is rebuilt here rather than generalised in place — the AI Console keeps
 * working untouched, and the two can be reconciled later if a third caller
 * appears.
 */
export default function InfoWindow({ title, kicker, mark, tabs, onClose }: Props) {
  const [active, setActive] = useState(tabs[0]?.id ?? '');
  const titleId = useId();

  // Escape closes, and the body is locked so the page behind does not scroll
  // under the window while it is open.
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    document.addEventListener('keydown', onKey);
    const previous = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = previous;
    };
  }, [onClose]);

  const shown = tabs.find((tab) => tab.id === active) ?? tabs[0];

  return (
    <div className={w.overlay}>
      {/* A button rather than a div: clicking away must be reachable by the
          same means as everything else, and it stays out of the tab order so
          it never steals focus from the content. */}
      <button
        type="button"
        className={w.backdrop}
        aria-label="Close"
        tabIndex={-1}
        onClick={onClose}
      />

      <div className={w.window} role="dialog" aria-modal="true" aria-labelledby={titleId}>
        <header className={w.head}>
          <div className={w.titleWrap}>
            {mark ? <span className={w.mark}>{mark}</span> : null}
            <div>
              <h2 id={titleId} className={w.title}>
                {title}
              </h2>
              {kicker ? <p className={w.kicker}>{kicker}</p> : null}
            </div>
          </div>
          <button type="button" className={w.close} aria-label="Close" onClick={onClose}>
            ×
          </button>
        </header>

        {tabs.length > 1 ? (
          <div className={w.tabs} role="tablist" aria-label={title}>
            {tabs.map((tab) => (
              <button
                key={tab.id}
                type="button"
                role="tab"
                aria-selected={tab.id === shown?.id}
                className={cx(w.tab, tab.id === shown?.id && w.tabActive)}
                onClick={() => setActive(tab.id)}
              >
                {tab.label}
              </button>
            ))}
          </div>
        ) : null}

        <div className={w.body}>{shown?.content}</div>
      </div>
    </div>
  );
}
