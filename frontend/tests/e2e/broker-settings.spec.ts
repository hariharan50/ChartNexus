import { expect, test, type Page } from '@playwright/test';

/**
 * Settings → Broker with two brokers (ADR 0002), and Zerodha's return trip.
 *
 * This page talks to the API from the browser, and the production build the
 * suite runs against has no `/api` proxy (see `trade-buddy-fixtures.ts`), so
 * the broker endpoints are fulfilled here. Nothing reaches a broker.
 */

function connection(broker: 'fyers' | 'kite', connected = false) {
  const callback = broker === 'kite' ? 'broker/kite/callback' : 'broker/callback';
  return {
    broker,
    status: connected ? 'active' : 'pending',
    configured: connected,
    connected,
    masked_app_id: connected ? 'abc1******89' : null,
    broker_user_id: connected ? 'AB1234' : null,
    display_name: connected ? 'Test Trader' : null,
    connected_at: null,
    last_validated_at: null,
    last_error: null,
    expires_at: null,
    client_id: null,
    redirect_uri: `http://localhost:5173/settings/${callback}`
  };
}

async function stubBrokerApi(page: Page): Promise<void> {
  await page.route('**/api/v1/broker/**', async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/broker/connections')) {
      return route.fulfill({
        json: { active_broker: null, connections: [connection('fyers'), connection('kite')] }
      });
    }
    const broker = url.pathname.includes('/broker/kite/') ? 'kite' : 'fyers';
    const completed = url.pathname.endsWith('/callback') && route.request().method() === 'POST';
    return route.fulfill({ json: connection(broker, completed) });
  });
}

test.beforeEach(async ({ context, baseURL, page }) => {
  await context.addCookies([
    { name: 'cn_session', value: 'test', url: baseURL ?? 'http://localhost:4173' }
  ]);
  await stubBrokerApi(page);
});

test('the picker offers both brokers and the one-at-a-time rule', async ({ page }) => {
  await page.goto('/settings/broker');

  await expect(page.getByRole('heading', { name: 'Broker integration' })).toBeVisible();
  const brokers = page.getByRole('list', { name: 'Brokers' });
  await expect(brokers.getByRole('button', { name: /^Zerodha Kite/ })).toBeVisible();
  await expect(brokers.getByRole('button', { name: /^FYERS/ })).toBeVisible();
  await expect(page.getByText('Only one broker can be connected at a time')).toBeVisible();
  // No form until a broker is chosen.
  await expect(page.getByLabel('API key')).toHaveCount(0);
});

test('choosing a broker opens its connection, and back returns to the picker', async ({ page }) => {
  await page.goto('/settings/broker');
  await page.getByRole('button', { name: /^Zerodha Kite/ }).click();

  await expect(page).toHaveURL('/settings/broker?broker=kite');
  await expect(page.getByRole('heading', { name: 'Broker connection' })).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Zerodha Kite' })).toBeVisible();
  await expect(page.getByLabel('API key')).toBeVisible();
  await expect(page.getByLabel('Zerodha Client ID (optional)')).toBeVisible();
  await expect(page.getByText('http://localhost:5173/settings/broker/kite/callback')).toBeVisible();

  await page.getByRole('button', { name: 'All brokers' }).click();
  await expect(page).toHaveURL('/settings/broker');
  await expect(page.getByRole('heading', { name: 'Broker integration' })).toBeVisible();

  await page.getByRole('button', { name: /^FYERS/ }).click();
  await expect(page.getByLabel('App ID')).toBeVisible();
  await expect(page.getByLabel('Zerodha Client ID (optional)')).toHaveCount(0);

  // The browser's own back button works the same way.
  await page.goBack();
  await expect(page).toHaveURL('/settings/broker');
});

test('the Kite callback posts the request token and scrubs the URL', async ({ page }) => {
  const posted = page.waitForRequest(
    (request) => request.url().endsWith('/broker/kite/callback') && request.method() === 'POST'
  );

  await page.goto(
    '/settings/broker/kite/callback?action=login&type=login&status=success' +
      '&request_token=rt-123&state=st-456'
  );

  const request = await posted;
  expect(request.postDataJSON()).toEqual({ auth_code: 'rt-123', state: 'st-456' });
  await expect(page).toHaveURL('/settings/broker?broker=kite&connected=1');
  await expect(page.getByText('Zerodha Kite connected.')).toBeVisible();
  expect(page.url()).not.toContain('rt-123');
});

test('a cancelled Kite login says so and posts nothing', async ({ page }) => {
  let posted = false;
  page.on('request', (request) => {
    if (request.url().endsWith('/broker/kite/callback') && request.method() === 'POST') {
      posted = true;
    }
  });

  await page.goto('/settings/broker/kite/callback?status=cancelled&state=st-456');

  await expect(page.getByRole('heading', { name: 'Connection failed' })).toBeVisible();
  await expect(page.getByText('Zerodha cancelled this connection.')).toBeVisible();
  expect(posted).toBe(false);
});
