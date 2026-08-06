import { useState } from 'react';
import IconEye from './icons/IconEye';
import IconEyeOff from './icons/IconEyeOff';
import IconLock from './icons/IconLock';
import s from './PasswordField.module.css';
import TextField from './TextField';

interface Props {
  label?: string | undefined;
  value: string;
  onValueChange?: ((value: string) => void) | undefined;
  placeholder?: string | undefined;
  error?: string | undefined;
  autocomplete?: 'current-password' | 'new-password' | undefined;
  required?: boolean | undefined;
  /** Forwarded to the field wrapper — see TextField. */
  className?: string | undefined;
}

export default function PasswordField({
  label = 'Password',
  value,
  onValueChange,
  placeholder = 'Enter your password',
  error,
  autocomplete = 'current-password',
  required = false,
  className
}: Props) {
  const [revealed, setRevealed] = useState(false);

  return (
    <TextField
      label={label}
      value={value}
      onValueChange={onValueChange}
      error={error}
      placeholder={placeholder}
      required={required}
      className={className}
      autoComplete={autocomplete}
      type={revealed ? 'text' : 'password'}
      icon={<IconLock />}
      trailing={
        <button
          type="button"
          className={s.toggle}
          onClick={() => setRevealed((current) => !current)}
          aria-pressed={revealed}
          aria-label={revealed ? 'Hide password' : 'Show password'}
          tabIndex={-1}
        >
          {revealed ? <IconEye /> : <IconEyeOff />}
        </button>
      }
    />
  );
}
