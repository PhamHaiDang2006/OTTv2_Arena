import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { CasualBoard, CasualLobby, CasualPlay, Modes } from '../src/casual';
import {
  botMove,
  loadGames,
  newGame,
  playMove,
  resign,
  saveGame,
  updateGame,
  type CasualGame,
} from '../src/casual-engine';
import { legalMoves, parseFen, toFen, applyMove, outcome } from '../replay-viewer/src';
import type { User } from '../../contracts/generated/types';

const user: User = {
  id: '00000001-0000-4000-8000-000000000001',
  email: 'casual@example.test',
  role: 'member',
  team_id: null,
  is_active: true,
};
// Deterministic stand-in for Math.random.
const seeded =
  (seed = 1) =>
  () => {
    seed = (seed * 16807) % 2147483647;
    return seed / 2147483647;
  };
const game = newGame('BLUE', 'random', seeded());
// jsdom has no Web Locks: a stand-in that queues requests until the test grants them, like a lock another tab holds.
function stubLocks() {
  const queue: (() => Promise<void>)[] = [];
  const request = vi.fn(
    (_name: string, granted: () => unknown) =>
      new Promise((resolve, reject) =>
        queue.push(() => Promise.resolve().then(granted).then(resolve, reject)),
      ),
  );
  Object.defineProperty(navigator, 'locks', { configurable: true, value: { request } });
  return { request, grant: () => queue.shift()!() };
}
beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.unstubAllGlobals();
  delete (navigator as { locks?: unknown }).locks;
});

it('offers Casual, local practice and Arena', () => {
  render(
    <MemoryRouter>
      <Modes />
    </MemoryRouter>,
  );
  expect(screen.getByText('Chơi với máy →').getAttribute('href')).toBe('/casual');
  expect(screen.getByText('Hướng dẫn tự luyện →').getAttribute('href')).toBe('/practice');
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
  render(<CasualBoard game={resign({ ...game, human_side: 'RED' })} busy={false} onMove={vi.fn()} />);
  expect(screen.getAllByRole('button')[0].getAttribute('aria-label')).toMatch(/^i1:/);
  expect(screen.getAllByRole('button').every((button) => (button as HTMLButtonElement).disabled)).toBe(true);
});

it('plays the human move and one bot reply without any network request', () => {
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  const next = playMove(game, 'c3d4', seeded(7));
  expect(next.moves.map((m) => [m.side, m.move])[0]).toEqual(['BLUE', 'c3d4']);
  expect(next.moves[1].side).toBe('RED');
  expect(next.ply).toBe(2);
  expect(next.turn).toBe('BLUE');
  expect(next.legal_moves.sort()).toEqual(legalMoves(parseFen(next.fen), 'BLUE').sort());
  expect(() => playMove(game, 'a1a2')).toThrow('Nước đi không hợp lệ.');
  expect(fetch).not.toHaveBeenCalled();
});

it('lets the bot open when the human plays red', () => {
  const red = newGame('RED', 'greedy', seeded());
  expect(red.moves).toHaveLength(1);
  expect(red.turn).toBe('RED');
});

it('greedy takes an immediate win', () => {
  const nearGoal: CasualGame = {
    ...game,
    fen: '9/k6B1/9/9/9/9/9/9/9',
    bot: 'greedy',
    turn: 'BLUE',
    legal_moves: legalMoves(parseFen('9/k6B1/9/9/9/9/9/9/9'), 'BLUE'),
  };
  expect(botMove(nearGoal, seeded(3))).toBe('h8i9');
});

it.each(['BLUE', 'RED'] as const)(
  'hard defends an immediate goal threat as %s instead of taking distant material',
  (side) => {
    const board = parseFen('9/9/7kp/6B2/9/9/B8/1k7/9');
    const position =
      side === 'BLUE'
        ? board
        : [...board]
            .reverse()
            .map((p) =>
              p ? ((p === p.toUpperCase() ? p.toLowerCase() : p.toUpperCase()) as typeof p) : null,
            );
    const state: CasualGame = {
      ...game,
      bot: 'hard',
      turn: side,
      fen: toFen(position),
      legal_moves: legalMoves(position, side),
    };
    expect(botMove({ ...state, bot: 'greedy' }, seeded())).toBe(side === 'BLUE' ? 'g6h7' : 'c4b3');
    const move = botMove(state, seeded());
    expect(move).toBe(side === 'BLUE' ? 'a3b2' : 'i7h8');
    const next = applyMove(position, move);
    const enemy = side === 'BLUE' ? 'RED' : 'BLUE';
    expect(
      legalMoves(next, enemy).some((reply) => outcome(applyMove(next, reply), enemy, 2, 300)?.[0] === enemy),
    ).toBe(false);
  },
);

it('hard takes a win immediately and respects the move limit', () => {
  const fen = '9/k6B1/9/9/9/9/9/9/9';
  const state: CasualGame = {
    ...game,
    bot: 'hard',
    fen,
    ply: 299,
    legal_moves: legalMoves(parseFen(fen), 'BLUE'),
  };
  const move = botMove(state, seeded());
  expect(outcome(applyMove(parseFen(fen), move), 'BLUE', 300, 300)?.[0]).toBe('BLUE');
});

it('preserves old bot settings and hard games in browser storage without network requests', () => {
  const fetch = vi.fn();
  vi.stubGlobal('fetch', fetch);
  for (const bot of ['random', 'greedy', 'hard'] as const) {
    const current = newGame('RED', bot, seeded());
    expect(current.turn).toBe('RED');
    expect(current.ply).toBe(1);
    saveGame(user.id, current);
    expect(loadGames(user.id).find((g) => g.id === current.id)).toEqual(current);
  }
  expect(loadGames(user.id)).toHaveLength(3);
  expect(fetch).not.toHaveBeenCalled();
});

it('saves games per account and plays a full game to a result', () => {
  let current = newGame('BLUE', 'random', seeded(11));
  saveGame(user.id, current);
  const random = seeded(5);
  while (current.status === 'playing') {
    current = playMove(
      current,
      current.legal_moves[Math.floor(random() * current.legal_moves.length)],
      random,
    );
    saveGame(user.id, current);
  }
  expect(['GOAL', 'WIPEOUT', 'STALEMATE', 'MOVE_LIMIT']).toContain(current.reason);
  expect(current.ply).toBe(current.moves.length);
  expect(loadGames(user.id)).toEqual([current]);
  expect(loadGames('another-user')).toEqual([]);
});

it('ignores corrupted storage', () => {
  localStorage.setItem(`ottv2.casual.v1:${user.id}`, '{not json');
  expect(loadGames(user.id)).toEqual([]);
  localStorage.setItem(`ottv2.casual.v1:${user.id}`, JSON.stringify([{ id: 'x', fen: 'bad' }, game]));
  expect(loadGames(user.id)).toEqual([game]);
});

it.each(['greedy', 'hard'] as const)(
  'creates with the selected %s bot and side then opens the game',
  async (bot) => {
    render(
      <MemoryRouter initialEntries={['/casual']}>
        <Routes>
          <Route path="/casual" element={<CasualLobby user={user} />} />
          <Route path="/casual/:id" element={<p>Opened game</p>} />
        </Routes>
      </MemoryRouter>,
    );
    fireEvent.click(
      screen.getByRole('button', {
        name: bot === 'greedy' ? /THỬ CHIẾN THUẬT Bot ưu tiên ăn quân/ : /THỬ THÁCH Bot chiến thuật/,
      }),
    );
    expect((screen.getByLabelText('Đối thủ') as HTMLSelectElement).value).toBe(bot);
    fireEvent.change(screen.getByLabelText('Màu quân của bạn'), { target: { value: 'RED' } });
    fireEvent.click(screen.getByText('Bắt đầu chơi'));
    await screen.findByText('Opened game');
    const [saved] = loadGames(user.id);
    expect([saved.bot, saved.human_side, saved.ply]).toEqual([bot, 'RED', 1]);
  },
);

it('confirms resignation and stores the result', async () => {
  saveGame(user.id, game);
  render(
    <MemoryRouter initialEntries={[`/casual/${game.id}`]}>
      <Routes>
        <Route path="/casual/:id" element={<CasualPlay user={user} />} />
      </Routes>
    </MemoryRouter>,
  );
  fireEvent.click(await screen.findByText('Đầu hàng'));
  expect(loadGames(user.id)[0].status).toBe('playing');
  fireEvent.click(screen.getByText('Xác nhận đầu hàng'));
  await waitFor(() => expect(screen.getByRole('status').textContent).toContain('Máy thắng'));
  expect(loadGames(user.id)[0]).toMatchObject({ status: 'finished', winner: 'RED', reason: 'RESIGNED' });
});

it('refuses a move when another tab already changed the game', async () => {
  saveGame(user.id, game);
  render(
    <MemoryRouter initialEntries={[`/casual/${game.id}`]}>
      <Routes>
        <Route path="/casual/:id" element={<CasualPlay user={user} />} />
      </Routes>
    </MemoryRouter>,
  );
  await screen.findByText('Đến lượt của bạn');
  saveGame(user.id, playMove(game, 'c3d4', seeded(2))); // the other tab, without a storage event
  fireEvent.click(screen.getByRole('button', { name: /^c3:/ }));
  fireEvent.click(screen.getByRole('button', { name: /^d4:/ }));
  expect((await screen.findByRole('alert')).textContent).toContain('tab khác');
  expect(loadGames(user.id)[0].ply).toBe(2);
});

it('re-reads the game under the cross-tab lock instead of overwriting a move made while waiting', async () => {
  saveGame(user.id, game);
  const locks = stubLocks();
  const mine = updateGame(user.id, game, resign);
  const refused = expect(mine).rejects.toThrow('tab khác');
  expect(locks.request).toHaveBeenCalledWith(`ottv2.casual.v1:${user.id}`, expect.any(Function));
  const other = playMove(game, 'c3d4', seeded(2));
  saveGame(user.id, other); // the other tab commits while this one waits for the lock
  await locks.grant();
  await refused;
  expect(loadGames(user.id)).toEqual([other]);
});

it('keeps the board disabled until the lock is granted', async () => {
  vi.useFakeTimers();
  saveGame(user.id, game);
  const locks = stubLocks();
  render(
    <MemoryRouter initialEntries={[`/casual/${game.id}`]}>
      <Routes>
        <Route path="/casual/:id" element={<CasualPlay user={user} />} />
      </Routes>
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole('button', { name: /^c3:/ }));
  fireEvent.click(screen.getByRole('button', { name: /^d4:/ }));
  const squares = () => screen.getAllByRole('button', { name: /^[a-i][1-9]:/ }) as HTMLButtonElement[];
  expect(squares().every((square) => square.disabled)).toBe(true);
  // Time alone must never release the board while another tab owns the lock.
  await act(async () => {
    await vi.advanceTimersByTimeAsync(5000);
  });
  expect(squares().every((square) => square.disabled)).toBe(true);
  expect(loadGames(user.id)[0].ply).toBe(0);
  await act(async () => {
    await locks.grant();
  });
  expect(loadGames(user.id)[0].ply).toBe(2);
  // Saving finishes before the human/bot animations; interaction stays locked.
  expect(squares().every((square) => square.disabled)).toBe(true);
  await act(async () => {
    await vi.runAllTimersAsync();
  });
  expect(squares().some((square) => !square.disabled)).toBe(true);
  expect(screen.getByRole('status').textContent).toBe('Đến lượt của bạn');
});

it('says when a game is not stored in this browser', () => {
  render(
    <MemoryRouter initialEntries={['/casual/missing']}>
      <Routes>
        <Route path="/casual/:id" element={<CasualPlay user={user} />} />
      </Routes>
    </MemoryRouter>,
  );
  expect(screen.getByText(/Không tìm thấy ván này trên trình duyệt/)).toBeTruthy();
});
