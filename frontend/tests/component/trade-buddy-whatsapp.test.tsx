import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type * as TradeBuddyData from '../../app/routes/terminal/tools/trade-buddy/trade-buddy-data';
import type { AlertChannelView } from '../../app/routes/terminal/tools/trade-buddy/trade-buddy-data';

/**
 * The per-user WhatsApp card. What matters: connecting sends the number and
 * key once, the connected card shows only the masked number, and a failure is
 * shown rather than swallowed.
 */
const connectWhatsApp = vi.fn();
const testWhatsApp = vi.fn();

vi.mock('../../app/routes/terminal/tools/trade-buddy/trade-buddy-data', async () => {
  const actual = await vi.importActual<typeof TradeBuddyData>(
    '../../app/routes/terminal/tools/trade-buddy/trade-buddy-data'
  );
  return {
    ...actual,
    connectWhatsApp: (...args: unknown[]) => connectWhatsApp(...args),
    testWhatsApp: (...args: unknown[]) => testWhatsApp(...args)
  };
});

const WhatsAppChannel = (
  await import('../../app/routes/terminal/tools/trade-buddy/components/WhatsAppChannel')
).default;

function view(overrides: Partial<AlertChannelView> = {}): AlertChannelView {
  return {
    channel: 'whatsapp',
    configured: true,
    ready: true,
    verified: true,
    enabled: true,
    label: 'WhatsApp (CallMeBot)',
    target: '…3210',
    masked_secret: 'call******3456',
    ...overrides
  };
}

function renderCard(whatsapp: AlertChannelView | undefined) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <WhatsAppChannel whatsapp={whatsapp} />
    </QueryClientProvider>
  );
}

describe('WhatsAppChannel', () => {
  beforeEach(() => {
    connectWhatsApp.mockReset();
    testWhatsApp.mockReset();
  });

  it('offers the connect form when nothing is connected', () => {
    renderCard(undefined);
    expect(screen.getByText(/Not connected/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Connect WhatsApp' })).toBeDisabled();
  });

  it('sends the number and key, trimmed, once', async () => {
    connectWhatsApp.mockResolvedValue(view());
    renderCard(undefined);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/WhatsApp number/), '  +91 98765 43210 ');
    await user.type(screen.getByLabelText(/CallMeBot API key/), ' key-123456 ');
    await user.click(screen.getByRole('button', { name: 'Connect WhatsApp' }));

    await waitFor(() => expect(connectWhatsApp).toHaveBeenCalledTimes(1));
    expect(connectWhatsApp).toHaveBeenCalledWith('+91 98765 43210', 'key-123456');
    expect(await screen.findByText(/welcome message has been sent/)).toBeInTheDocument();
  });

  it('shows the server’s reason when connecting fails', async () => {
    connectWhatsApp.mockRejectedValue(new Error('Enter the WhatsApp number in international form'));
    renderCard(undefined);
    const user = userEvent.setup();

    await user.type(screen.getByLabelText(/WhatsApp number/), '98765 43210');
    await user.type(screen.getByLabelText(/CallMeBot API key/), 'key-123456');
    await user.click(screen.getByRole('button', { name: 'Connect WhatsApp' }));

    expect(await screen.findByText(/international form/)).toBeInTheDocument();
  });

  it('shows only the masked number once connected, and hides the form', () => {
    renderCard(view());
    expect(screen.getByText('…3210')).toBeInTheDocument();
    expect(screen.queryByLabelText(/WhatsApp number/)).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Send test message' })).toBeInTheDocument();
  });

  it('says paused when switched off', () => {
    renderCard(view({ enabled: false, ready: false }));
    expect(screen.getByText(/Paused/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Resume alerts' })).toBeInTheDocument();
  });
});
