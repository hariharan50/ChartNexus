import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import Select, { type SelectOption } from '../../app/lib/shared/ui/Select';

/**
 * The app's dropdown.
 *
 * It replaced the native `<select>` everywhere, so what is pinned here is the
 * part of the native control that had to survive the trade: the keyboard
 * contract, a disabled option that cannot be chosen, and a control that names
 * itself. The look is the reason it exists; the behaviour is the risk.
 */
const OPTIONS: SelectOption[] = [
  { value: 'near', label: '27 Oct 2026', meta: '26d', hint: 'Near month' },
  { value: 'next', label: '23 Nov 2026', meta: '53d', hint: 'Next month' },
  { value: 'far', label: '29 Dec 2026', meta: '89d', hint: 'Far month', disabled: true }
];

function open() {
  return userEvent.click(screen.getByRole('button', { name: 'Expiry' }));
}

function renderSelect(props: Partial<React.ComponentProps<typeof Select>> = {}) {
  const onChange = vi.fn();
  render(
    <Select
      value="near"
      options={OPTIONS}
      onChange={onChange}
      ariaLabel="Expiry"
      {...(props as Record<string, never>)}
    />
  );
  return onChange;
}

describe('Select', () => {
  it('shows the selected option on the trigger and keeps the list closed', () => {
    renderSelect();

    expect(screen.getByRole('button', { name: 'Expiry' })).toHaveTextContent('27 Oct 2026');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('opens on click and ticks the current value', async () => {
    renderSelect();
    await open();

    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(3);
    expect(options[0]).toHaveAttribute('aria-selected', 'true');
    expect(options[1]).toHaveAttribute('aria-selected', 'false');
  });

  it('carries the two secondary columns the native control could not', async () => {
    renderSelect();
    await open();

    expect(screen.getAllByRole('option')[0]).toHaveTextContent('26d');
    expect(screen.getAllByRole('option')[0]).toHaveTextContent('Near month');
  });

  it('reports the chosen value and closes', async () => {
    const onChange = renderSelect();
    await open();
    await userEvent.click(screen.getAllByRole('option')[1]!);

    expect(onChange).toHaveBeenCalledWith('next');
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('refuses a disabled option rather than reporting it', async () => {
    const onChange = renderSelect();
    await open();
    await userEvent.click(screen.getAllByRole('option')[2]!);

    expect(onChange).not.toHaveBeenCalled();
    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });

  it('opens on the arrow keys and chooses with Enter', async () => {
    const onChange = renderSelect();
    screen.getByRole('button', { name: 'Expiry' }).focus();

    await userEvent.keyboard('{ArrowDown}');
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    // Focus starts on the selected row, so one step down is the next option.
    await userEvent.keyboard('{ArrowDown}{Enter}');

    expect(onChange).toHaveBeenCalledWith('next');
  });

  it('dismisses on Escape and gives focus back to the trigger', async () => {
    renderSelect();
    await open();

    await userEvent.keyboard('{Escape}');

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Expiry' })).toHaveFocus();
  });

  it('falls back to the placeholder when the value matches nothing', () => {
    renderSelect({ value: 'gone', placeholder: 'Nearest expiry' });

    expect(screen.getByRole('button', { name: 'Expiry' })).toHaveTextContent('Nearest expiry');
  });

  it('cannot be opened with no options to offer', async () => {
    renderSelect({ options: [] });

    const trigger = screen.getByRole('button', { name: 'Expiry' });
    expect(trigger).toBeDisabled();
    await userEvent.click(trigger);
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('closes when a click lands outside it', async () => {
    render(
      <div>
        <Select value="near" options={OPTIONS} onChange={() => {}} ariaLabel="Expiry" />
        <button type="button">elsewhere</button>
      </div>
    );
    await open();

    await userEvent.click(screen.getByRole('button', { name: 'elsewhere' }));

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  // Every options page keeps a one-second clock for its countdowns, so the
  // owner re-renders while the list is open and hands down a freshly built
  // `options` array each time. Closing on that array's identity made the popup
  // vanish a second after it was opened, on every dropdown in the terminal.
  it('stays open when its owner re-renders with an equal options list', async () => {
    const owner = () => (
      <Select
        value="near"
        options={OPTIONS.map((option) => ({ ...option }))}
        onChange={() => {}}
        ariaLabel="Expiry"
      />
    );
    const { rerender } = render(owner());
    await open();

    rerender(owner());

    expect(screen.getByRole('listbox')).toBeInTheDocument();
  });

  it('closes when the rows themselves change', async () => {
    const owner = (rows: SelectOption[]) => (
      <Select value="near" options={rows} onChange={() => {}} ariaLabel="Expiry" />
    );
    const { rerender } = render(owner(OPTIONS));
    await open();

    rerender(owner(OPTIONS.slice(1)));

    expect(screen.queryByRole('listbox')).not.toBeInTheDocument();
  });

  it('drives a controlled value through its owner', async () => {
    function Harness() {
      const [value, setValue] = useState('near');
      return <Select value={value} options={OPTIONS} onChange={setValue} ariaLabel="Expiry" />;
    }
    render(<Harness />);

    await open();
    await userEvent.click(screen.getAllByRole('option')[1]!);

    expect(screen.getByRole('button', { name: 'Expiry' })).toHaveTextContent('23 Nov 2026');
  });
});
