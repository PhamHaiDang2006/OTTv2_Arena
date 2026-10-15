import { routes, type Operations } from './generated/operations';
import type { Error as ApiErrorBody } from './generated/types';

export class ApiError extends Error {
  constructor(public status: number, public payload: ApiErrorBody | null) {
    super(payload?.error.message ?? `HTTP ${status}`);
  }
}
export interface RequestOptions {
  baseUrl?: string;
  accessToken?: string;
  idempotencyKey?: string;
  workerLeaseToken?: string;
  path?: Record<string, string>;
  query?: Record<string, string | number | undefined>;
  signal?: AbortSignal;
  fetchImpl?: typeof fetch;
}
/** Transport helper only: shared app owns refresh/retry and runtime validation. */
export async function request<K extends keyof Operations>(
  operation: K,
  body: K extends 'createSubmission' ? FormData : Operations[K]['request'],
  options: RequestOptions = {},
): Promise<Operations[K]['response']> {
  const route = routes[operation];
  const resolvedPath = route.path.replace(/\{([^}]+)\}/g, (_, key: string) => {
    const value = options.path?.[key];
    if (!value) throw new Error(`Missing path parameter: ${key}`);
    return encodeURIComponent(value);
  });
  const query = new URLSearchParams();
  for (const [key, value] of Object.entries(options.query ?? {})) {
    if (value !== undefined) query.set(key, String(value));
  }
  const headers: Record<string, string> = {};
  if (options.accessToken) headers.Authorization = `Bearer ${options.accessToken}`;
  if (options.idempotencyKey) headers['Idempotency-Key'] = options.idempotencyKey;
  if (options.workerLeaseToken) headers['X-Worker-Lease'] = options.workerLeaseToken;
  const multipart = body instanceof FormData;
  if (body !== undefined && !multipart) headers['Content-Type'] = 'application/json';
  const url = (options.baseUrl ?? '/api/v1').replace(/\/$/, '') + resolvedPath + (query.size ? '?' + query : '');
  const response = await (options.fetchImpl ?? fetch)(url, {
    method: route.method, headers, credentials: 'include', signal: options.signal,
    body: body === undefined ? undefined : multipart ? body : JSON.stringify(body),
  });
  if (!response.ok) {
    const payload = await response.json().catch(() => null) as ApiErrorBody | null;
    throw new ApiError(response.status, payload);
  }
  return (response.status === 204 ? undefined : await response.json()) as Operations[K]['response'];
}
