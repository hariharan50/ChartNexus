import { normalisePhoneDigits } from '$shared/validation/phone';
import IconPhone from './icons/IconPhone';
import TextField from './TextField';

/**
 * An Indian mobile number field.
 *
 * `value` holds the ten national digits — the country code is fixed at +91
 * and shown as a prefix rather than typed, so there is nothing to strip and
 * no way to enter a number the backend would reject on its dialling code.
 */
interface Props {
  label?: string | undefined;
  value: string;
  onValueChange?: ((value: string) => void) | undefined;
  error?: string | undefined;
  required?: boolean | undefined;
}

const NATIONAL_LENGTH = 10;

export default function PhoneField({
  label = 'Phone number',
  value,
  onValueChange,
  error,
  required = false
}: Props) {
  /**
   * Keep the reported value to bare digits whatever gets typed or pasted — a
   * pasted "+91 98765 43210" should land as "9876543210" rather than be
   * rejected for containing spaces. The input is controlled, so React puts the
   * cleaned value back on screen even when the typed character was dropped.
   */
  function handleChange(next: string) {
    onValueChange?.(normalisePhoneDigits(next).slice(0, NATIONAL_LENGTH));
  }

  return (
    <TextField
      label={label}
      value={value}
      onValueChange={handleChange}
      error={error}
      required={required}
      type="tel"
      inputMode="numeric"
      autoComplete="tel-national"
      placeholder="9876543210"
      maxLength={NATIONAL_LENGTH}
      icon={<IconPhone />}
      leading="+91"
    />
  );
}
