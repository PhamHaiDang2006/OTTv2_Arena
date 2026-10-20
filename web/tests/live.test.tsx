import { afterEach, expect, it, vi } from 'vitest';
import { act, cleanup, render } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useLive } from '../src/live';
import { session } from '../src/api';
import auth from '../../contracts/examples/http/login.response.json';
import type { Auth } from '../../contracts/generated/types';
class FakeSocket {
  static OPEN = 1;
  static sockets: FakeSocket[] = [];
  readyState = 1;
  onopen?: () => void;
  onmessage?: (event: { data: string }) => void;
  onclose?: (event: { code: number }) => void;
  sent: string[] = [];
  constructor(public url: string) {
    FakeSocket.sockets.push(this);
  }
  send(value: string) {
    this.sent.push(value);
  }
  close() {
    this.onclose?.({ code: 1000 });
  }
}
afterEach(() => {
  cleanup();
  session.set(null);
  FakeSocket.sockets = [];
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
it('authenticates before team subscription, deduplicates events, and refetches on reconnect', async () => {
  vi.useFakeTimers();
  vi.stubGlobal('WebSocket', FakeSocket);
  session.set(auth as Auth);
  const client = new QueryClient(),
    invalidate = vi.spyOn(client, 'invalidateQueries');
  function Harness() {
    useLive(session.user());
    return null;
  }
  render(
    <QueryClientProvider client={client}>
      <Harness />
    </QueryClientProvider>,
  );
  const socket = FakeSocket.sockets[0];
  act(() => socket.onopen?.());
  expect(socket.url).not.toContain('token');
  expect(socket.sent.map((x) => JSON.parse(x).channel)).not.toContain(`team:${auth.user.team_id}`);
  act(() => socket.onmessage?.({ data: '{"type":"auth.ok"}' }));
  expect(socket.sent.map((x) => JSON.parse(x).channel)).toContain(`team:${auth.user.team_id}`);
  const event = {
    schema_version: 1,
    event_id: '00000001-0000-4000-8000-000000000001',
    type: 'announcement.published',
    channel: 'public',
    occurred_at: '2026-10-20T00:00:00Z',
    data: { announcement_id: '00000001-0000-4000-8000-000000000002' },
  };
  act(() => {
    socket.onmessage?.({ data: JSON.stringify(event) });
    socket.onmessage?.({ data: JSON.stringify(event) });
  });
  expect(invalidate).toHaveBeenCalledTimes(2);
  act(() => socket.close());
  await act(async () => {
    await vi.advanceTimersByTimeAsync(1600);
  });
  expect(FakeSocket.sockets).toHaveLength(2);
  act(() => FakeSocket.sockets[1].onopen?.());
  expect(invalidate).toHaveBeenCalledTimes(3);
});
