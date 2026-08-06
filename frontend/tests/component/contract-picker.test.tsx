import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { act } from 'react';
import { describe, expect, it, vi } from 'vitest';
import ContractPicker from '../../app/routes/terminal/options/multi-oi-volume/components/ContractPicker';
import type { ContractSeries } from '../../app/routes/terminal/options/multi-oi-volume/multi-oi-data';

/**
 * The Custom Strikes dialog.
 *
 * It sits over a page that is still polling and redrawing, so the focus
 * behaviour is not decoration: losing focus into the background leaves a
 * keyboard user tabbing through charts they cannot see.
 */

function contract(strike: number, option_type: 'CE' | 'PE', oi = 100, volume = 10): ContractSeries {
  return { id: `${strike}${option_type}`, strike, option_type, oi: [oi], volume: [volume] };
}

const CONTRACTS = [
  contract(24_600, 'CE'),
  contract(24_600, 'PE'),
  contract(24_650, 'CE'),
  contract(24_700, 'PE')
];

function setup(overrides: Partial<Parameters<typeof ContractPicker>[0]> = {}) {
  const onApply = vi.fn();
  const onClose = vi.fn();
  const utils = render(
    <ContractPicker
      contracts={CONTRACTS}
      selected={[]}
      title="High OI contracts"
      onApply={onApply}
      onClose={onClose}
      {...overrides}
    />
  );
  return { ...utils, onApply, onClose };
}

function press(key: string) {
  act(() => {
    document.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));
  });
}

describe('ContractPicker', () => {
  it('lists every contract it is given', () => {
    setup();
    const dialog = screen.getByRole('dialog');

    expect(within(dialog).getByText('24600 CE')).toBeTruthy();
    expect(within(dialog).getByText('24700 PE')).toBeTruthy();
  });

  it('filters by strike as you type', async () => {
    const user = userEvent.setup();
    setup();

    await user.type(screen.getByLabelText('Search strike'), '24700');

    expect(screen.queryByText('24600 CE')).toBeNull();
    expect(screen.getByText('24700 PE')).toBeTruthy();
  });

  it('filters by side', async () => {
    setup();

    await act(async () => {
      screen.getByRole('button', { name: 'PE', pressed: false }).click();
    });

    expect(screen.queryByText('24600 CE')).toBeNull();
    expect(screen.getByText('24600 PE')).toBeTruthy();
  });

  it('multi-selects and applies the chosen ids', async () => {
    const { onApply } = setup();

    await act(async () => {
      screen.getByText('24600 CE').click();
    });
    await act(async () => {
      screen.getByText('24700 PE').click();
    });
    await act(async () => {
      screen.getByRole('button', { name: 'Apply' }).click();
    });

    expect(onApply).toHaveBeenCalledWith(['24600CE', '24700PE']);
  });

  it('deselects on a second click', async () => {
    const { onApply } = setup({ selected: ['24600CE'] });

    await act(async () => {
      screen.getByText('24600 CE').click();
    });
    await act(async () => {
      screen.getByRole('button', { name: 'Apply' }).click();
    });

    expect(onApply).toHaveBeenCalledWith([]);
  });

  it('closes on Escape without applying', () => {
    const { onApply, onClose } = setup();

    press('Escape');

    expect(onClose).toHaveBeenCalled();
    expect(onApply).not.toHaveBeenCalled();
  });

  it('moves focus into the search field on open', () => {
    setup();

    expect(document.activeElement).toBe(screen.getByLabelText('Search strike'));
  });

  it('returns focus to whatever opened it', () => {
    // Otherwise focus lands back at the top of a live, polling document.
    const opener = document.createElement('button');
    document.body.appendChild(opener);
    opener.focus();

    const { unmount } = setup();
    unmount();

    expect(document.activeElement).toBe(opener);
    opener.remove();
  });

  it('reports how many are selected', async () => {
    setup({ selected: ['24600CE'] });

    expect(screen.getByText(/1 of 10 selected/)).toBeTruthy();
  });

  it('clears the whole selection', async () => {
    const { onApply } = setup({ selected: ['24600CE', '24700PE'] });

    await act(async () => {
      screen.getByRole('button', { name: 'Clear' }).click();
    });
    await act(async () => {
      screen.getByRole('button', { name: 'Apply' }).click();
    });

    expect(onApply).toHaveBeenCalledWith([]);
  });

  it('says so when nothing matches', async () => {
    const user = userEvent.setup();
    setup();

    await user.type(screen.getByLabelText('Search strike'), '99999');

    expect(screen.getByText('No contracts match.')).toBeTruthy();
  });
});
