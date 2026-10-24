import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { RoomPage, RoomsLobby } from '../src/rooms';
import { session } from '../src/api';
import type { Room, User } from '../../contracts/generated/types';
import fixture from '../../contracts/examples/http/createRoom.response.json';

const user: User = {
  id: fixture.players[0].id,
  email: 'host@example.test',
  role: 'member',
  team_id: null,
  is_active: true,
};
const initial = fixture as Room;
const clients: QueryClient[] = [];
afterEach(() => {
  cleanup();
  clients.splice(0).forEach((c) => c.clear());
  session.set(null);
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});
function open(path: string) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  clients.push(client);
  session.set({ access_token: 'test', token_type: 'bearer', expires_in: 900, user });
  render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/rooms" element={<RoomsLobby user={user} />} />
          <Route path="/rooms/:id" element={<RoomPage user={user} />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return client;
}
const json = (value: unknown, status = 200) => new Response(JSON.stringify(value), { status });
it('uses invite codes, joins explicitly, and opens the durable room', async () => {
  const fetch = vi.fn(async (url: string, opts?: RequestInit) => {
    if (url.endsWith('/join')) {
      expect(JSON.parse(opts!.body as string)).toEqual({ code: 'ABCDEFGH' });
      return json(initial);
    }
    return json(url === '/api/v1/rooms' ? [] : initial);
  });
  vi.stubGlobal('fetch', fetch);
  open('/rooms?invite=abcdefgh');
  expect((screen.getByLabelText('Mã mời') as HTMLInputElement).value).toBe('ABCDEFGH');
  fireEvent.click(screen.getByRole('button', { name: 'Vào phòng' }));
  expect(await screen.findByRole('button', { name: 'Sẵn sàng' })).toBeTruthy();
  expect(screen.getByLabelText('Link mời')).toBeTruthy();
});
it.each(['standard', 'hexagon', 'circular'] as const)(
  'creates a %s room through the shared API',
  async (map) => {
    const fetch = vi.fn(async (_url: string, opts?: RequestInit) => {
      if (opts?.method === 'POST') {
        expect(JSON.parse(opts.body as string)).toEqual({ map });
        return json({ ...initial, map }, 201);
      }
      return json(_url === '/api/v1/rooms' ? [] : { ...initial, map });
    });
    vi.stubGlobal('fetch', fetch);
    open('/rooms');
    fireEvent.change(screen.getByLabelText('Bản đồ'), { target: { value: map } });
    fireEvent.click(screen.getByRole('button', { name: 'Tạo phòng hai người' }));
    expect(await screen.findByRole('button', { name: 'Sẵn sàng' })).toBeTruthy();
  },
);
it('submits readiness with revision, then restores a newer snapshot on reconnect', async () => {
  let state = structuredClone(initial);
  const fetch = vi.fn(async (url: string, opts?: RequestInit) => {
    if (url.endsWith('/commands')) {
      expect(JSON.parse(opts!.body as string)).toEqual({ revision: 0, action: 'ready' });
      state = { ...state, revision: 1, players: [{ ...state.players[0], ready: true }] };
    }
    return json(state);
  });
  vi.stubGlobal('fetch', fetch);
  open(`/rooms/${initial.id}`);
  fireEvent.click(await screen.findByRole('button', { name: 'Sẵn sàng' }));
  await waitFor(() =>
    expect((screen.getByRole('button', { name: 'Hủy sẵn sàng' }) as HTMLButtonElement).disabled).toBe(false),
  );
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(false);
  fireEvent(window, new Event('offline'));
  expect((screen.getByRole('button', { name: 'Hủy sẵn sàng' }) as HTMLButtonElement).disabled).toBe(true);
  state = {
    ...state,
    revision: 2,
    status: 'playing',
    turn: 'BLUE',
    legal_moves: [{ from: 'a3', to: 'a4' }],
    players: [
      ...state.players,
      { id: '00000000-0000-4000-8000-000000000099', side: 'RED', ready: true, rematch: false },
    ],
  };
  vi.spyOn(navigator, 'onLine', 'get').mockReturnValue(true);
  fireEvent(window, new Event('online'));
  expect(await screen.findByText('Lượt của bạn')).toBeTruthy();
  fireEvent.click(screen.getByRole('button', { name: /a3:/ }));
  expect(screen.getByRole('button', { name: /a4:.*có thể đi tới/ })).toBeTruthy();
});
it('requests rematch only once and waits for the other player', async () => {
  let state: Room = {
    ...structuredClone(initial),
    status: 'finished',
    result: { winner: 'BLUE', reason: 'RESIGNED' },
  };
  let commands = 0;
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      if (url.endsWith('/commands')) {
        commands++;
        state = { ...state, revision: 1, players: [{ ...state.players[0], rematch: true }] };
      }
      return json(state);
    }),
  );
  open(`/rooms/${state.id}`);
  fireEvent.click(await screen.findByRole('button', { name: 'Chơi lại' }));
  const waiting = await screen.findByRole('button', { name: 'Đợi bạn đồng ý chơi lại…' });
  expect((waiting as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(waiting);
  expect(commands).toBe(1);
});
