import { apiFetch } from '$shared/api/client';
import type { AuthenticationResult, GoogleAuthorization, SessionSummary, User } from './types';

/**
 * Thin wrappers over the auth endpoints.
 *
 * The server sets httpOnly cookies on every one of these responses, so the
 * tokens in the body are ignored by the browser app — they exist for
 * non-browser clients. Nothing here writes a token to storage.
 */

/** `identifier` is an email address or a phone number — the API tells them apart. */
export function login(identifier: string, password: string): Promise<AuthenticationResult> {
  return apiFetch<AuthenticationResult>({
    url: '/auth/login',
    method: 'POST',
    body: JSON.stringify({ identifier, password })
  });
}

export function register(input: {
  email: string;
  password: string;
  phone: string;
  displayName?: string;
}): Promise<AuthenticationResult> {
  return apiFetch<AuthenticationResult>({
    url: '/auth/register',
    method: 'POST',
    body: JSON.stringify({
      email: input.email,
      password: input.password,
      phone: input.phone,
      display_name: input.displayName ?? ''
    })
  });
}

export function refresh(): Promise<AuthenticationResult> {
  return apiFetch<AuthenticationResult>({
    url: '/auth/refresh',
    method: 'POST',
    body: JSON.stringify({})
  });
}

export function logout(): Promise<{ message: string }> {
  return apiFetch({ url: '/auth/logout', method: 'POST', body: JSON.stringify({}) });
}

export function logoutEverywhere(): Promise<{ revoked: number }> {
  return apiFetch({ url: '/auth/logout-all', method: 'POST', body: JSON.stringify({}) });
}

export function currentUser(fetcher?: typeof fetch): Promise<User> {
  return apiFetch<User>({ url: '/auth/me', fetcher });
}

export function listSessions(): Promise<SessionSummary[]> {
  return apiFetch<SessionSummary[]>({ url: '/auth/sessions' });
}

export function startGoogleLogin(redirectTo?: string): Promise<GoogleAuthorization> {
  return apiFetch<GoogleAuthorization>({
    url: '/auth/google/authorize',
    method: 'POST',
    body: JSON.stringify({ redirect_to: redirectTo ?? null })
  });
}

export function completeGoogleLogin(code: string, state: string): Promise<AuthenticationResult> {
  return apiFetch<AuthenticationResult>({
    url: '/auth/google/callback',
    method: 'POST',
    body: JSON.stringify({ code, state })
  });
}
