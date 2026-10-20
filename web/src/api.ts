import { ApiError, request, type RequestOptions } from '../../contracts/client';
import { routes, type Operations } from '../../contracts/generated/operations';
import type { Auth, User } from '../../contracts/generated/types';
import operations from '../../contracts/operations.json';
import { validate } from '../shared/schema';
export { ApiError };
export type Op = keyof Operations;
let token: string | undefined;
let user: User | null = null;
let generation = 0;
let refreshing: Promise<Auth> | undefined;
const listeners = new Set<() => void>();
export const session = {
  user: () => user,
  token: () => token,
  subscribe: (listener: () => void) => {
    listeners.add(listener);
    return () => {
      listeners.delete(listener);
    };
  },
  set: (auth: Auth | null) => {
    token = auth?.access_token;
    user = auth?.user ?? null;
    listeners.forEach((listener) => listener());
  },
};
const baseUrl = import.meta.env.VITE_API_BASE_URL || '/api/v1';
export async function refresh(): Promise<Auth> {
  if (!refreshing) {
    const current = generation;
    refreshing = request('refresh', undefined, { baseUrl })
      .then((raw) => {
        const auth = validate<Auth>('Auth', raw);
        if (current !== generation) throw new Error('Phiên đăng nhập đã thay đổi.');
        session.set(auth);
        return auth;
      })
      .catch((error) => {
        if (current === generation) session.set(null);
        throw error;
      })
      .finally(() => {
        refreshing = undefined;
      });
  }
  return refreshing;
}
export async function signOut() {
  generation++;
  try {
    await request('logout', undefined, { baseUrl });
  } finally {
    session.set(null);
  }
}
export async function api<K extends Op>(
  op: K,
  body: K extends 'createSubmission' ? FormData : Operations[K]['request'],
  options: RequestOptions = {},
): Promise<Operations[K]['response']> {
  const mutation = routes[op].method !== 'GET';
  const idempotencyKey = mutation ? (options.idempotencyKey ?? crypto.randomUUID()) : undefined;
  const usedToken = token;
  const send = () => request(op, body, { ...options, baseUrl, accessToken: token, idempotencyKey });
  let result: Operations[K]['response'];
  try {
    result = await send();
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401 || ['login', 'refresh', 'logout'].includes(op))
      throw error;
    // Another request may already have rotated the token. Replay only once, with the same key.
    if (token === usedToken) await refresh();
    result = await send();
  }
  const schema = operations.find((item) => item.operationId === op)?.response;
  return schema ? validate<Operations[K]['response']>(schema, result) : result;
}
export function errorText(error: unknown) {
  if (error instanceof ApiError) {
    const prefix: Record<number, string> = {
      401: 'Phiên đăng nhập đã hết hạn.',
      403: 'Bạn không có quyền thực hiện thao tác này.',
      404: 'Chưa có dữ liệu này.',
      409: 'Trạng thái đã thay đổi. Dữ liệu đang được tải lại.',
      429: 'Đã hết hạn mức hoặc gửi quá nhiều yêu cầu. Vui lòng thử lại sau.',
    };
    return `${prefix[error.status] ?? 'Không thực hiện được yêu cầu.'} ${error.payload?.error.message ?? ''}`;
  }
  if (error instanceof TypeError)
    return 'Mất kết nối. Với thao tác vừa gửi, kết quả chưa xác định; hãy tải lại danh sách trước khi gửi lại.';
  return error instanceof Error ? error.message : 'Đã xảy ra lỗi. Vui lòng thử lại.';
}
