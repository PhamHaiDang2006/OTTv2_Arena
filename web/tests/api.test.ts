import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { api, session } from '../src/api';
import auth from '../../contracts/examples/http/login.response.json';
import accepted from '../../contracts/examples/http/createScrimmage.response.json';
import quota from '../../contracts/examples/http/scrimmageQuota.response.json';
import type { Auth } from '../../contracts/generated/types';
const response = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
const unauthorized = () =>
  response({ error: { code: 'UNAUTHORIZED', message: 'Expired', details: {} }, request_id: 'test' }, 401);
beforeEach(() => session.set({ ...auth, access_token: 'old' } as Auth));
afterEach(() => {
  vi.unstubAllGlobals();
  session.set(null);
});
describe('shared authenticated transport', () => {
  it('coalesces concurrent refresh and retains idempotency key on one replay', async () => {
    const calls: { url: string; headers: Record<string, string> }[] = [];
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init: RequestInit) => {
        const headers = init.headers as Record<string, string>;
        calls.push({ url, headers });
        if (url.endsWith('/auth/refresh')) {
          await new Promise((r) => setTimeout(r, 10));
          return response({ ...auth, access_token: 'new' });
        }
        if (headers.Authorization === 'Bearer old') return unauthorized();
        return response(url.endsWith('/quota') ? quota : accepted);
      }),
    );
    await Promise.all([
      api('createScrimmage', { opponent_team_id: '00000002-0000-4000-8000-000000000002' }),
      api('scrimmageQuota', undefined),
    ]);
    expect(calls.filter((c) => c.url.endsWith('/auth/refresh'))).toHaveLength(1);
    const mutation = calls.filter((c) => c.url.endsWith('/scrimmages'));
    expect(mutation).toHaveLength(2);
    expect(mutation[0].headers['Idempotency-Key']).toBe(mutation[1].headers['Idempotency-Key']);
  });
  it('does not retry mutation network failures', async () => {
    const mock = vi.fn().mockRejectedValue(new TypeError('Network'));
    vi.stubGlobal('fetch', mock);
    await expect(api('createScrimmage', { opponent_team_id: 'test' })).rejects.toThrow();
    expect(mock).toHaveBeenCalledTimes(1);
  });
  it('clears session on refresh rejection without looping', async () => {
    const mock = vi.fn().mockImplementation(async () => unauthorized());
    vi.stubGlobal('fetch', mock);
    await expect(api('scrimmageQuota', undefined)).rejects.toThrow();
    expect(mock).toHaveBeenCalledTimes(2);
    expect(session.user()).toBeNull();
  });
  it('rejects a malformed successful response', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(response({ remaining: 5 })));
    await expect(api('scrimmageQuota', undefined)).rejects.toThrow('hợp đồng');
  });
});
