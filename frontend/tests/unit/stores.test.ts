import { beforeEach, describe, expect, it } from 'vitest';
import { useNotificationPreferencesStore } from '$shared/ui/notification-preferences-store';
import { usePreferencesStore } from '$shared/ui/preferences-store';
import { selectIsDark, useThemeStore } from '$shared/ui/theme-store';

/**
 * The three preference stores are the only migrated state that reaches outside
 * React — they write localStorage and attributes on <html>. That contract, and
 * the "defaults until init() runs" rule that keeps hydration clean, is what
 * these pin down.
 */

const theme = () => useThemeStore.getState();
const prefs = () => usePreferencesStore.getState();
const notify = () => useNotificationPreferencesStore.getState();

beforeEach(() => {
  localStorage.clear();
  document.documentElement.setAttribute('data-theme', 'dark');
  document.documentElement.removeAttribute('data-callput');
  useThemeStore.setState({ theme: 'dark' });
  usePreferencesStore.setState({ showChartTooltip: true, callPutScheme: 'classic' });
  useNotificationPreferencesStore.setState({
    toggles: {
      priceAlerts: true,
      oiAlerts: true,
      brokerStatus: true,
      marketSchedule: true,
      productUpdates: false,
      weeklyDigest: false
    },
    pushTimeout: '10'
  });
});

describe('theme store', () => {
  it('defaults to dark, matching what the server rendered', () => {
    expect(theme().theme).toBe('dark');
    expect(selectIsDark(theme())).toBe(true);
  });

  it('adopts a stored theme on init', () => {
    localStorage.setItem('cn-theme', 'warm');
    theme().init();
    expect(theme().theme).toBe('warm');
    expect(document.documentElement.getAttribute('data-theme')).toBe('warm');
  });

  it('falls back to the rendered attribute when storage is empty', () => {
    document.documentElement.setAttribute('data-theme', 'terminal');
    theme().init();
    expect(theme().theme).toBe('terminal');
  });

  it('rejects an unknown stored value rather than trusting it', () => {
    localStorage.setItem('cn-theme', 'neon');
    theme().init();
    expect(theme().theme).toBe('dark');
  });

  it('persists and mirrors onto the document when set', () => {
    theme().set('light');
    expect(localStorage.getItem('cn-theme')).toBe('light');
    expect(document.documentElement.getAttribute('data-theme')).toBe('light');
    expect(selectIsDark(useThemeStore.getState())).toBe(false);
  });

  it('toggle flips between light and dark from any theme', () => {
    theme().set('warm'); // a light-surface theme
    theme().toggle();
    expect(useThemeStore.getState().theme).toBe('dark');

    theme().toggle();
    expect(useThemeStore.getState().theme).toBe('light');
  });
});

describe('preferences store', () => {
  it('defaults to a visible tooltip and the classic call/put scheme', () => {
    expect(prefs().showChartTooltip).toBe(true);
    expect(prefs().callPutScheme).toBe('classic');
  });

  it('treats absent tooltip storage as on, not off', () => {
    prefs().init();
    expect(usePreferencesStore.getState().showChartTooltip).toBe(true);
  });

  it('adopts stored values on init and mirrors the scheme onto the document', () => {
    localStorage.setItem('cn-pref-chart-tooltip', '0');
    localStorage.setItem('cn-pref-callput', 'inverted');
    prefs().init();

    expect(usePreferencesStore.getState().showChartTooltip).toBe(false);
    expect(usePreferencesStore.getState().callPutScheme).toBe('inverted');
    expect(document.documentElement.getAttribute('data-callput')).toBe('inverted');
  });

  it('rejects an unknown scheme', () => {
    localStorage.setItem('cn-pref-callput', 'rainbow');
    prefs().init();
    expect(usePreferencesStore.getState().callPutScheme).toBe('classic');
  });

  it('persists each setter', () => {
    prefs().setShowChartTooltip(false);
    expect(localStorage.getItem('cn-pref-chart-tooltip')).toBe('0');

    prefs().setCallPutScheme('inverted');
    expect(localStorage.getItem('cn-pref-callput')).toBe('inverted');
    expect(document.documentElement.getAttribute('data-callput')).toBe('inverted');
  });
});

describe('notification preferences store', () => {
  it('starts from the defaults', () => {
    expect(notify().toggles.priceAlerts).toBe(true);
    expect(notify().toggles.weeklyDigest).toBe(false);
    expect(notify().pushTimeout).toBe('10');
  });

  it('merges stored toggles over the defaults, so a new toggle still has one', () => {
    localStorage.setItem('cn-pref-notifications', JSON.stringify({ priceAlerts: false }));
    notify().init();

    const { toggles } = useNotificationPreferencesStore.getState();
    expect(toggles.priceAlerts).toBe(false);
    expect(toggles.oiAlerts).toBe(true);
  });

  it('falls back to the defaults when stored json is corrupt', () => {
    localStorage.setItem('cn-pref-notifications', '{not json');
    notify().init();
    expect(useNotificationPreferencesStore.getState().toggles.priceAlerts).toBe(true);
  });

  it('persists a single toggle without disturbing the others', () => {
    notify().set('weeklyDigest', true);

    const stored = JSON.parse(localStorage.getItem('cn-pref-notifications') ?? '{}');
    expect(stored.weeklyDigest).toBe(true);
    expect(stored.priceAlerts).toBe(true);
  });

  it('persists the push timeout', () => {
    notify().setPushTimeout('off');
    expect(localStorage.getItem('cn-pref-push-timeout')).toBe('off');
    expect(useNotificationPreferencesStore.getState().pushTimeout).toBe('off');
  });
});
