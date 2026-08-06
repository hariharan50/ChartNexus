/**
 * Indian mobile number helpers.
 *
 * Mirrors the backend's `PhoneNumber` value object so the signup form can say
 * "that number isn't valid" before a round trip. The backend stays
 * authoritative — this only exists to make the form feel immediate.
 */

const DIALLING_CODE = '+91';
const NATIONAL_LENGTH = 10;

/** Indian mobiles are ten digits opening 6-9. */
const NATIONAL_PATTERN = /^[6-9]\d{9}$/;

/**
 * Reduce anything a person might type to the ten national digits.
 *
 * Accepts `9876543210`, `+91 98765 43210`, `09876543210` and `919876543210`,
 * matching the spellings the backend normalises.
 */
export function normalisePhoneDigits(raw: string): string {
  const digits = (raw ?? '').replace(/\D/g, '');

  if (digits.length === NATIONAL_LENGTH + 2 && digits.startsWith('91')) return digits.slice(2);
  if (digits.length === NATIONAL_LENGTH + 1 && digits.startsWith('0')) return digits.slice(1);
  return digits;
}

export function isValidIndianMobile(digits: string): boolean {
  return NATIONAL_PATTERN.test(digits);
}

/** The stored form: `+919876543210`. */
export function toE164(digits: string): string {
  return `${DIALLING_CODE}${normalisePhoneDigits(digits)}`;
}
