import { browser } from '$app/environment';

export type PushTimeout = '5' | '10' | '30' | '60' | 'off';

export interface NotificationToggleKey {
  priceAlerts: boolean;
  oiAlerts: boolean;
  brokerStatus: boolean;
  marketSchedule: boolean;
  productUpdates: boolean;
  weeklyDigest: boolean;
}

const DEFAULTS: NotificationToggleKey = {
  priceAlerts: true,
  oiAlerts: true,
  brokerStatus: true,
  marketSchedule: true,
  productUpdates: false,
  weeklyDigest: false
};

const STORAGE_KEY = 'mc-pref-notifications';
const TIMEOUT_KEY = 'mc-pref-push-timeout';

/**
 * Notification toggles, persisted per-browser in localStorage.
 *
 * No backend endpoint exists for these yet, so this mirrors the theme/display
 * preference stores: same seam, so an account-level `user_preferences` row can
 * back it later without the settings page changing.
 */
class NotificationPreferencesStore {
  #toggles = $state<NotificationToggleKey>({ ...DEFAULTS });
  #pushTimeout = $state<PushTimeout>('10');

  get toggles(): NotificationToggleKey {
    return this.#toggles;
  }

  get pushTimeout(): PushTimeout {
    return this.#pushTimeout;
  }

  init(): void {
    if (!browser) return;
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        this.#toggles = { ...DEFAULTS, ...JSON.parse(stored) };
      } catch {
        this.#toggles = { ...DEFAULTS };
      }
    }
    const timeout = localStorage.getItem(TIMEOUT_KEY) as PushTimeout | null;
    this.#pushTimeout = timeout ?? '10';
  }

  set<K extends keyof NotificationToggleKey>(key: K, value: NotificationToggleKey[K]): void {
    this.#toggles = { ...this.#toggles, [key]: value };
    if (browser) localStorage.setItem(STORAGE_KEY, JSON.stringify(this.#toggles));
  }

  setPushTimeout(value: PushTimeout): void {
    this.#pushTimeout = value;
    if (browser) localStorage.setItem(TIMEOUT_KEY, value);
  }
}

export const notificationPreferences = new NotificationPreferencesStore();
