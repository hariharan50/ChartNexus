import { describe, expect, it } from 'vitest';
import { isValidIndianMobile, normalisePhoneDigits, toE164 } from '$shared/validation/phone';

/**
 * These mirror the backend's PhoneNumber value object. If the two ever
 * disagree the form will accept a number the API then rejects, so the accepted
 * spellings here are deliberately the same list as the backend's.
 */
describe('normalisePhoneDigits', () => {
  it.each([
    ['9876543210', 'bare national'],
    ['+919876543210', 'already E.164'],
    ['09876543210', 'trunk prefix'],
    ['919876543210', 'country code, no plus'],
    ['+91 98765 43210', 'spaced'],
    ['+91-98765-43210', 'hyphenated'],
    ['(+91) 98765 43210', 'parenthesised']
  ])('reduces %s (%s) to the ten national digits', (typed) => {
    expect(normalisePhoneDigits(typed)).toBe('9876543210');
  });

  it('strips anything that is not a digit', () => {
    expect(normalisePhoneDigits('98abc76543210xyz')).toBe('9876543210');
  });

  it('survives an empty value rather than throwing', () => {
    expect(normalisePhoneDigits('')).toBe('');
  });
});

describe('isValidIndianMobile', () => {
  it.each(['6876543210', '7876543210', '8876543210', '9876543210'])(
    'accepts %s — Indian mobiles open 6-9',
    (digits) => {
      expect(isValidIndianMobile(digits)).toBe(true);
    }
  );

  it.each([
    ['', 'empty'],
    ['987654321', 'nine digits'],
    ['98765432101', 'eleven digits'],
    ['1234567890', 'starts with 1'],
    ['5876543210', 'starts with 5'],
    ['98765abcde', 'letters']
  ])('rejects %s (%s)', (digits) => {
    expect(isValidIndianMobile(digits)).toBe(false);
  });
});

describe('toE164', () => {
  it('prefixes the dialling code onto the national digits', () => {
    expect(toE164('9876543210')).toBe('+919876543210');
  });

  it('normalises first, so any accepted spelling produces one stored form', () => {
    expect(toE164('+91 98765 43210')).toBe('+919876543210');
    expect(toE164('09876543210')).toBe('+919876543210');
  });
});
