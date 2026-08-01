/**
 * The API answers every failure with the same RFC 9457 problem document, so
 * the UI has exactly one error shape to handle.
 * See backend `infrastructure/transport/http/exception_handlers.py`.
 */

export interface Problem {
  type: string;
  title: string;
  status: number;
  detail: string;
  code: string;
  request_id?: string;
  errors?: Array<{ field: string; reason: string }>;
  retry_after_seconds?: number;
}

export class ApiError extends Error {
  readonly problem: Problem;
  readonly status: number;

  constructor(problem: Problem, status: number) {
    super(problem.detail);
    this.name = 'ApiError';
    this.problem = problem;
    this.status = status;
  }

  get code(): string {
    return this.problem.code;
  }

  get requestId(): string | undefined {
    return this.problem.request_id;
  }

  /** Field-level messages, keyed by field name, for form rendering. */
  get fieldErrors(): Record<string, string> {
    const result: Record<string, string> = {};
    for (const { field, reason } of this.problem.errors ?? []) result[field] = reason;
    return result;
  }

  /** Re-authentication will not help — do not bounce the user to login. */
  get isTerminal(): boolean {
    return this.status < 500 && this.status !== 401 && this.status !== 429;
  }
}

export async function parseProblem(response: Response): Promise<Problem> {
  try {
    const body = (await response.json()) as Partial<Problem>;
    return {
      type: body.type ?? 'about:blank',
      title: body.title ?? response.statusText,
      status: body.status ?? response.status,
      detail: body.detail ?? response.statusText,
      code: body.code ?? 'unknown_error',
      ...(body.request_id !== undefined ? { request_id: body.request_id } : {}),
      ...(body.errors !== undefined ? { errors: body.errors } : {}),
      ...(body.retry_after_seconds !== undefined
        ? { retry_after_seconds: body.retry_after_seconds }
        : {})
    };
  } catch {
    // A proxy timeout or gateway error returns HTML, not a problem document.
    return {
      type: 'about:blank',
      title: response.statusText || 'Request failed',
      status: response.status,
      detail: `The server returned ${response.status}.`,
      code: response.status >= 500 ? 'internal_error' : 'request_failed'
    };
  }
}

export function isApiError(error: unknown): error is ApiError {
  return error instanceof ApiError;
}
