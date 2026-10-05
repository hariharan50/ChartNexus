import { create } from 'zustand';

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

const STORAGE_KEY = 'cn-pref-notifications';
const TIMEOUT_KEY = 'cn-pref-push-timeout';

interface NotificationPreferencesState {
  toggles: NotificationToggleKey;
  pushTimeout: PushTimeout;
  init: () => void;
  set: <K extends keyof NotificationToggleKey>(key: K, value: NotificationToggleKey[K]) => void;
  setPushTimeout: (value: PushTimeout) => void;
}

/**
 * Notification toggles, persisted per-browser in localStorage.
 *
 * No backend endpoint exists for these yet, so this mirrors the theme/display
 * preference stores: same seam, so an account-level `user_preferences` row can
 * back it later without the settings page changing.
 *
 * See the SSR-singleton note in theme-store.ts: never set from render.
 */
export const useNotificationPreferencesStore = create<NotificationPreferencesState>()(
  (setState, get) => ({
    toggles: { ...DEFAULTS },
    pushTimeout: '10',

    init: () => {
      if (typeof document === 'undefined') return;

      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        try {
          setState({
            toggles: { ...DEFAULTS, ...(JSON.parse(stored) as Partial<NotificationToggleKey>) }
          });
        } catch {
          setState({ toggles: { ...DEFAULTS } });
        }
      }

      const timeout = localStorage.getItem(TIMEOUT_KEY) as PushTimeout | null;
      setState({ pushTimeout: timeout ?? '10' });
    },

    set: (key, value) => {
      const toggles = { ...get().toggles, [key]: value };
      setState({ toggles });
      if (typeof document === 'undefined') return;
      localStorage.setItem(STORAGE_KEY, JSON.stringify(toggles));
    },

    setPushTimeout: (value) => {
      setState({ pushTimeout: value });
      if (typeof document === 'undefined') return;
      localStorage.setItem(TIMEOUT_KEY, value);
    }
  })
);
