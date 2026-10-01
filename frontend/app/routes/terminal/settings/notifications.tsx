import { useEffect, useRef, useState } from 'react';
import {
  useNotificationPreferencesStore,
  type NotificationToggleKey,
  type PushTimeout
} from '$shared/ui/notification-preferences-store';
import { cx } from '$shared/ui/cx';
import Select from '$shared/ui/Select';
import s from './notifications.module.css';
import type { Route } from './+types/notifications';

export const meta: Route.MetaFunction = () => [
  { title: 'Notifications · Settings · MarketCompass' }
];

interface ToggleDef {
  key: keyof NotificationToggleKey;
  title: string;
  hint: string;
}

const accountToggles: ToggleDef[] = [
  {
    key: 'priceAlerts',
    title: 'Price alerts',
    hint: 'When an instrument you track crosses a price level you set.'
  },
  {
    key: 'oiAlerts',
    title: 'Open interest & PCR alerts',
    hint: 'When OI build-up, PCR or max-pain shifts sharply on your watchlist.'
  },
  {
    key: 'brokerStatus',
    title: 'Broker connection',
    hint: 'When your FYERS session expires or a reconnect is needed.'
  },
  {
    key: 'marketSchedule',
    title: 'Market schedule',
    hint: 'Pre-open, open and close reminders for NSE trading sessions.'
  }
];

const emailToggles: ToggleDef[] = [
  {
    key: 'productUpdates',
    title: 'Product updates',
    hint: 'New indicators, tools and terminal features as they ship.'
  },
  {
    key: 'weeklyDigest',
    title: 'Weekly digest',
    hint: 'A Monday summary of your watchlist and open positions.'
  }
];

const pushTimeouts: { id: PushTimeout; label: string }[] = [
  { id: '5', label: '5 Minutes' },
  { id: '10', label: '10 Minutes' },
  { id: '30', label: '30 Minutes' },
  { id: '60', label: '1 Hour' },
  { id: 'off', label: 'Off' }
];

export default function SettingsNotifications() {
  const toggles = useNotificationPreferencesStore((state) => state.toggles);
  const pushTimeout = useNotificationPreferencesStore((state) => state.pushTimeout);
  const setToggle = useNotificationPreferencesStore((state) => state.set);
  const setStoredTimeout = useNotificationPreferencesStore((state) => state.setPushTimeout);

  const [savedVisible, setSavedVisible] = useState(false);
  const hideTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // A pending timer would otherwise set state on an unmounted page.
  useEffect(() => () => clearTimeout(hideTimer.current), []);

  function flashSaved() {
    setSavedVisible(true);
    clearTimeout(hideTimer.current);
    hideTimer.current = setTimeout(() => setSavedVisible(false), 1400);
  }

  function toggle(key: keyof NotificationToggleKey) {
    setToggle(key, !toggles[key]);
    flashSaved();
  }

  function handleTimeoutChange(value: string) {
    setStoredTimeout(value as PushTimeout);
    flashSaved();
  }

  const renderToggleRow = (row: ToggleDef, index: number) => (
    <div className={cx(s.row, index === 0 && s.first)} key={row.key}>
      <div className={s.copy}>
        <p className={s.label}>{row.title}</p>
        <p className={s.hint}>{row.hint}</p>
      </div>
      <button
        type="button"
        role="switch"
        aria-checked={toggles[row.key]}
        aria-label={row.title}
        className={cx(s.switch, toggles[row.key] && s.on)}
        onClick={() => toggle(row.key)}
      >
        <span className={s.knob} />
      </button>
    </div>
  );

  return (
    <>
      <header className={s.pageHeader}>
        <h1>Notifications</h1>
        <span className={cx(s.saved, savedVisible && s.visible)} role="status">
          <span className={s.dot} aria-hidden="true" />
          Saved
        </span>
      </header>

      <section className={s.group}>
        <p className={s.groupTitle}>Account notifications</p>

        {accountToggles.map(renderToggleRow)}

        <div className={cx(s.row, s.selectRow)}>
          <div className={s.copy}>
            <p className={s.label}>Push notification time-out</p>
            <p className={s.hint}>
              How long an in-app alert stays visible before it dismisses itself.
            </p>
          </div>
          <Select
            className={s.select}
            ariaLabel="Push notification time-out"
            value={pushTimeout}
            onChange={handleTimeoutChange}
            options={pushTimeouts.map((opt) => ({ value: opt.id, label: opt.label }))}
          />
        </div>
      </section>

      <section className={s.group}>
        <p className={s.groupTitle}>Email notifications</p>

        {emailToggles.map(renderToggleRow)}
      </section>
    </>
  );
}
