import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import PasswordField from '$shared/ui/PasswordField';
import PhoneField from '$shared/ui/PhoneField';
import TextField from '$shared/ui/TextField';

/**
 * `TextField` was the app's one `$bindable` component. Losing two-way binding
 * is the biggest behavioural change in the leaf UI kit, so the controlled
 * contract that replaced it is pinned here — along with the label and ARIA
 * wiring, which the migration must not have disturbed.
 */

function Controlled({ initial = '', error }: { initial?: string; error?: string }) {
  const [value, setValue] = useState(initial);
  return <TextField label="Email" value={value} onValueChange={setValue} error={error} />;
}

describe('TextField', () => {
  it('associates the label with the input without being given an id', () => {
    render(<TextField label="Email" value="" />);
    // getByLabelText only resolves when for/id actually match.
    expect(screen.getByLabelText('Email')).toBeInTheDocument();
  });

  it('honours an explicit id over the generated one', () => {
    render(<TextField label="Email" value="" id="custom-field" />);
    expect(screen.getByLabelText('Email')).toHaveAttribute('id', 'custom-field');
  });

  it('reports every keystroke to the owner', async () => {
    const user = userEvent.setup();
    const onValueChange = vi.fn();
    render(<TextField label="Email" value="" onValueChange={onValueChange} />);

    await user.type(screen.getByLabelText('Email'), 'ab');

    expect(onValueChange).toHaveBeenCalledTimes(2);
    expect(onValueChange).toHaveBeenNthCalledWith(1, 'a');
  });

  it('renders what the owner holds, not what was typed', async () => {
    const user = userEvent.setup();
    // No onValueChange: the value is pinned, so the field must not drift.
    render(<TextField label="Email" value="pinned" />);

    const input = screen.getByLabelText('Email');
    await user.type(input, 'xyz');

    expect(input).toHaveValue('pinned');
  });

  it('round-trips through a controlled owner', async () => {
    const user = userEvent.setup();
    render(<Controlled />);

    await user.type(screen.getByLabelText('Email'), 'hello');
    expect(screen.getByLabelText('Email')).toHaveValue('hello');
  });

  it('is not marked invalid when there is no error', () => {
    render(<Controlled />);
    const input = screen.getByLabelText('Email');
    expect(input).not.toHaveAttribute('aria-invalid');
    expect(input).not.toHaveAttribute('aria-describedby');
  });

  it('wires aria-invalid and aria-describedby to the error text', () => {
    render(<Controlled error="That address is already taken" />);

    const input = screen.getByLabelText('Email');
    expect(input).toHaveAttribute('aria-invalid', 'true');

    const describedBy = input.getAttribute('aria-describedby');
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy!)).toHaveTextContent(
      'That address is already taken'
    );
  });

  it('renders leading content unhidden and the icon hidden', () => {
    render(
      <TextField
        label="Phone"
        value=""
        icon={<span data-testid="icon">i</span>}
        leading={<span data-testid="leading">+91</span>}
      />
    );

    expect(screen.getByTestId('icon').closest('[aria-hidden="true"]')).not.toBeNull();
    expect(screen.getByTestId('leading').closest('[aria-hidden="true"]')).toBeNull();
  });
});

describe('PasswordField', () => {
  it('masks by default and reveals on request', async () => {
    const user = userEvent.setup();
    render(<PasswordField value="hunter2" />);

    const input = screen.getByLabelText('Password');
    expect(input).toHaveAttribute('type', 'password');

    await user.click(screen.getByRole('button', { name: 'Show password' }));
    expect(input).toHaveAttribute('type', 'text');

    await user.click(screen.getByRole('button', { name: 'Hide password' }));
    expect(input).toHaveAttribute('type', 'password');
  });

  it('keeps the reveal toggle out of the tab order', () => {
    render(<PasswordField value="" />);
    expect(screen.getByRole('button', { name: 'Show password' })).toHaveAttribute('tabindex', '-1');
  });
});

describe('PhoneField', () => {
  it('reduces a pasted international number to ten national digits', async () => {
    const user = userEvent.setup();
    const onValueChange = vi.fn();
    render(<PhoneField value="" onValueChange={onValueChange} />);

    await user.click(screen.getByLabelText('Phone number'));
    await user.paste('+91 98765 43210');

    expect(onValueChange).toHaveBeenLastCalledWith('9876543210');
  });

  it('drops characters that are not digits', async () => {
    const user = userEvent.setup();
    const onValueChange = vi.fn();
    render(<PhoneField value="" onValueChange={onValueChange} />);

    await user.click(screen.getByLabelText('Phone number'));
    await user.paste('98abc76');

    expect(onValueChange).toHaveBeenLastCalledWith('9876');
  });
});
