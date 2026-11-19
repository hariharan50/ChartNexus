import { isApiError } from '$shared/api/errors';

/**
 * Turns an API failure into something worth showing a person.
 *
 * The backend's messages are already user-facing, so most codes pass straight
 * through; the ones listed here need a different tone, or an action the API
 * cannot know about.
 */

interface Presented {
  message: string;
  /** Field to highlight, when the failure is about one input. */
  field?: string;
  /** Optional next step, rendered as a link beside the message. */
  action?: { label: string; href: string };
}

const OVERRIDES: Record<string, Presented> = {
  invalid_credentials: {
    // Names no identifier in particular: sign-in accepts either an email
    // address or a phone number, and saying which one was wrong would confirm
    // whether an account exists.
    message: 'Those sign-in details do not match an account.'
  },
  email_taken: {
    message: 'An account with this email already exists.',
    field: 'email',
    action: { label: 'Sign in instead', href: '/login' }
  },
  phone_taken: {
    message: 'An account with this phone number already exists.',
    field: 'phone',
    action: { label: 'Sign in instead', href: '/login' }
  },
  email_unverified: {
    message: 'Check your inbox and verify your email address before signing in.'
  },
  use_sso: {
    message: 'This account signs in with Google. Use the Google button below.'
  },
  session_revoked: {
    message: 'That session was ended for security reasons. Please sign in again.'
  },
  session_expired: {
    message: 'Your session expired. Please sign in again.'
  },
  rate_limited: {
    message: 'Too many attempts. Wait a few minutes and try again.'
  },
  registration_disabled: {
    message: 'New sign-ups are closed right now.'
  },
  oauth_state_invalid: {
    message: 'That sign-in link expired. Start again.',
    action: { label: 'Back to sign in', href: '/login' }
  },
  domain_not_allowed: {
    message: 'Your organisation does not permit sign-in with this account.'
  }
};

export function presentAuthError(error: unknown): Presented {
  if (!isApiError(error)) {
    return {
      message:
        error instanceof TypeError
          ? 'Could not reach the server. Check your connection and try again.'
          : 'Something went wrong. Please try again.'
    };
  }

  // 502/503/504 come from whatever sits in front of the API (Vite's proxy in
  // development, nginx in production) when the API itself is down or
  // restarting. "The server returned 502" tells nobody what to do.
  if (error.status >= 502 && error.status <= 504) {
    return {
      message:
        "Can't reach the ChartNexus server right now. It may be restarting — try again in a moment."
    };
  }

  // An unhandled backend exception. Outside production its detail is the raw
  // exception text (driver errors, hosts, ports), which means nothing to a
  // person and should not be on screen anyway. The request id lets support
  // find the stack trace in the logs.
  if (error.code === 'internal_error') {
    const reference = error.requestId ? ` (reference ${error.requestId})` : '';
    return {
      message: `Something went wrong on our side. Please try again in a moment.${reference}`
    };
  }

  const override = OVERRIDES[error.code];
  if (override) return override;

  // Field-level validation: surface the first message against its input.
  const fields = error.fieldErrors;
  const firstField = Object.keys(fields)[0];
  if (firstField) {
    return { message: fields[firstField] ?? error.message, field: firstField };
  }

  return { message: error.problem.detail };
}

/** Password rules, shown before the server has to reject anything. */
export function describePasswordPolicy(minLength = 12): string {
  return `At least ${minLength} characters. Avoid common passwords and your email address.`;
}
