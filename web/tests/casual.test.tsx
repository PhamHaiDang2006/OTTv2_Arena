import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { CasualBoard, CasualLobby, CasualPlay, Modes } from '../src/casual';
import type { CasualGame } from '../../contracts/generated/types';
import fixture from '../../contracts/examples/http/getCasualGame.response.json';

const game = fixture as CasualGame;
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status });
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it('offers two separate modes', () => {
  render(
    <MemoryRouter>
      <Modes />
    </MemoryRouter>,
  );
  expect(screen.getByText('Chơi với máy →').getAttribute('href')).toBe('/casual');
  expect(screen.getByText('Vào Arena →').getAttribute('href')).toBe('/arena');
});

it('only submits highlighted legal moves and disables the board while waiting', () => {
  const move = vi.fn();
  const view = render(<CasualBoard game={game} busy={false} onMove={move} />);
  expect((screen.getByRole('button', { name: /^a1:/ }) as HTMLButtonElement).disabled).toBe(true);
  fireEvent.click(screen.getByRole('button', { name: /^c3:/ }));
  fireEvent.click(screen.getByRole('button', { name: /^d4:/ }));
  expect(move).toHaveBeenCalledWith('c3d4');
  view.rerender(<CasualBoard game={game} busy={true} onMove={move} />);
  expect(screen.getAllByRole('button').every((button) => (button as HTMLButtonElement).disabled)).toBe(true);
});

it('orients red at the bottom and makes finished games read only', () => {
  render(
    <CasualBoard
      game={{
        ...game,
        human_side: 'RED',
        status: 'finished',
        turn: null,
        legal_moves: [],
        winner: 'BLUE',
        reason: 'RESIGNED',
      }}
      busy={false}
      onMove={vi.fn()}
    />,
  );
  expect(screen.getAllByRole('button')[0].getAttribute('aria-label')).toMatch(/^i1:/);
  expect(screen.getAllByRole('button').every((button) => (button as HTMLButtonElement).disabled)).toBe(true);
});

it('creates with the selected bot and side then opens the game', async () => {
  const fetch = vi.fn(async (_url: string, init?: RequestInit) =>
    init?.method === 'POST' ? json(game, 201) : json({ items: [], page: 1, page_size: 20, total: 0 }),
  );
  vi.stubGlobal('fetch', fetch);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={['/casual']}>
        <Routes>
          <Route path="/casual" element={<CasualLobby />} />
          <Route path="/casual/:id" element={<p>Opened game</p>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.change(screen.getByLabelText('Đối thủ'), { target: { value: 'greedy' } });
  fireEvent.change(screen.getByLabelText('Màu quân của bạn'), { target: { value: 'RED' } });
  fireEvent.click(screen.getByText('Bắt đầu chơi'));
  await screen.findByText('Opened game');
  const request = fetch.mock.calls.find(([, init]) => init?.method === 'POST')!;
  expect(request[0]).toBe('/api/v1/casual/games');
  expect(JSON.parse(request[1]!.body as string)).toEqual({ human_side: 'RED', bot: 'greedy' });
});

it('confirms resignation and renders the authoritative result', async () => {
  const fetch = vi.fn(async (_url: string, init?: RequestInit) =>
    json(
      init?.method === 'POST'
        ? { ...game, status: 'finished', winner: 'RED', reason: 'RESIGNED', turn: null, legal_moves: [] }
        : game,
    ),
  );
  vi.stubGlobal('fetch', fetch);
  render(
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
      <MemoryRouter initialEntries={[`/casual/${game.id}`]}>
        <Routes>
          <Route path="/casual/:id" element={<CasualPlay />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  fireEvent.click(await screen.findByText('Đầu hàng'));
  expect(fetch.mock.calls.filter(([, init]) => init?.method === 'POST')).toHaveLength(0);
  fireEvent.click(screen.getByText('Xác nhận đầu hàng'));
  await waitFor(() => expect(screen.getByRole('status').textContent).toContain('Máy thắng'));
  const request = fetch.mock.calls.find(([, init]) => init?.method === 'POST')!;
  expect(request[0]).toBe(`/api/v1/casual/games/${game.id}/resign`);
  expect(JSON.parse(request[1]!.body as string)).toEqual({ expected_ply: 0 });
});
