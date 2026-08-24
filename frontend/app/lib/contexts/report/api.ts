import { apiFetch } from '$shared/api/client';
import type { ReportAvailability, ReportEnrollment } from './types';

/** Daily market report — availability, the scheduled opt-in, and on-demand PDF. */

export function getReportAvailability(fetcher?: typeof fetch): Promise<ReportAvailability> {
  return apiFetch<ReportAvailability>({ url: '/report/availability', fetcher });
}

export function getReportEnrollment(fetcher?: typeof fetch): Promise<ReportEnrollment> {
  return apiFetch<ReportEnrollment>({ url: '/report/enrollment', fetcher });
}

export function setReportEnrollment(enabled: boolean): Promise<ReportEnrollment> {
  return apiFetch<ReportEnrollment>({
    url: '/report/enrollment',
    method: 'PUT',
    body: JSON.stringify({ enabled })
  });
}

const GENERATE_PATH = (symbol: string) => `/api/v1/report/${encodeURIComponent(symbol)}/generate`;
const CSRF_COOKIE = 'mc_csrf';
const CSRF_HEADER = 'X-CSRF-Token';
const REFRESH_PATH = '/api/v1/auth/refresh';

/**
 * Generate today's report on demand and trigger a browser download of the PDF.
 * Uses a raw fetch (not apiFetch) because the response is a binary blob, with the
 * same CSRF header + one silent refresh-and-retry the other POSTs use.
 */
export async function downloadReport(symbol: string): Promise<void> {
  let response = await postGenerate(symbol);
  if (response.status === 401) {
    const refreshed = await refreshOnce();
    if (refreshed) response = await postGenerate(symbol);
  }
  if (!response.ok) {
    throw new Error(`Report generation failed (${response.status})`);
  }
  const blob = await response.blob();
  const filename = filenameFrom(response) ?? `MarketCompass-${symbol}.pdf`;
  triggerDownload(blob, filename);
}

function postGenerate(symbol: string): Promise<Response> {
  const headers = new Headers({ accept: 'application/pdf' });
  const token = readCookie(CSRF_COOKIE);
  if (token) headers.set(CSRF_HEADER, token);
  return fetch(GENERATE_PATH(symbol), { method: 'POST', headers, credentials: 'include' });
}

function filenameFrom(response: Response): string | null {
  const cd = response.headers.get('content-disposition');
  const match = cd?.match(/filename="?([^"]+)"?/);
  return match?.[1] ?? null;
}

function triggerDownload(blob: Blob, filename: string): void {
  if (typeof document === 'undefined') return;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
}

async function refreshOnce(): Promise<boolean> {
  if (typeof document === 'undefined') return false;
  try {
    const res = await fetch(REFRESH_PATH, {
      method: 'POST',
      headers: { 'content-type': 'application/json', accept: 'application/json' },
      body: '{}',
      credentials: 'include'
    });
    return res.ok;
  } catch {
    return false;
  }
}

function readCookie(name: string): string | null {
  if (typeof document === 'undefined') return null;
  const match = document.cookie.match(
    new RegExp(`(?:^|;\\s*)${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}=([^;]*)`)
  );
  return match?.[1] ? decodeURIComponent(match[1]) : null;
}
