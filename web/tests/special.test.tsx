import { afterEach, expect, it, vi } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import {
  cells,
  chooseMove,
  frame,
  goals,
  initialPosition,
  listSpecial,
  moved,
  movesFor,
  newSpecial,
  parseSpecial,
  playSpecial,
  readSpecial,
  resultFor,
  specialKey,
  storeSpecial,
  type MapId,
} from '../src/special-engine';
import { SpecialBoard, SpecialLobby, SpecialPlay } from '../src/special';
import { Modes } from '../src/casual';
import type { User } from '../../contracts/generated/types';
const user: User = {
  id: 'special-test',
  email: 'test@example.test',
  role: 'member',
  team_id: null,
  is_active: true,
};
afterEach(() => {
  cleanup();
  localStorage.clear();
  vi.unstubAllGlobals();
});

it.each(['hexagon', 'ring'] as const)(
  '%s is symmetric, connected and starts with four of each piece per side',
  (map) => {
    const board = cells(map),
      ids = new Set(board.map((c) => c.id));
    expect(board).toHaveLength(map === 'hexagon' ? 91 : 84);
    const initial = initialPosition(map);
    for (const p of ['B', 'P', 'K', 'b', 'p', 'k'])
      expect(Object.values(initial).filter((v) => v === p)).toHaveLength(4);
    for (const c of board) {
      const opposite = `${-c.q},${-c.r}`;
      expect(ids.has(opposite)).toBe(true);
      if (initial[c.id]) expect(initial[opposite]?.toUpperCase()).toBe(initial[c.id].toUpperCase());
    }
    const visited = new Set<string>([goals.RED]),
      queue = [goals.RED];
    for (let i = 0; i < queue.length; i++) {
      // RED may enter its own goal and cannot enter BLUE's; include that endpoint separately.
      for (const m of movesFor(map, { [queue[i]]: 'K' }, 'BLUE'))
        if (!visited.has(m.to)) {
          visited.add(m.to);
          queue.push(m.to);
        }
    }
    expect(visited.size).toBe(board.length);
  },
);

it('has six neighbors, respects RPS and never crosses the missing center or board edge', () => {
  expect(movesFor('hexagon', { '0,0': 'B' }, 'BLUE')).toHaveLength(6);
  const p = { '0,0': 'B', '1,0': 'k', '1,-1': 'p', '0,-1': 'b', '-1,0': 'P' } as const;
  const moves = movesFor('hexagon', p, 'BLUE').filter((m) => m.from === '0,0');
  expect(moves.map((m) => m.to)).toEqual(expect.arrayContaining(['1,0', '-1,1', '0,1']));
  expect(moves).toHaveLength(3);
  expect(movesFor('ring', { '2,0': 'B' }, 'BLUE').map((m) => m.to)).not.toContain('1,0');
  expect(
    movesFor('hexagon', { '5,0': 'B' }, 'BLUE').every((m) => cells('hexagon').some((c) => c.id === m.to)),
  ).toBe(true);
});

it.each(['hexagon', 'ring'] as const)(
  '%s detects goals, captures, stalemate and move-limit results',
  (map) => {
    expect(resultFor(map, { '0,-5': 'B', '0,4': 'p' }, 'BLUE', 1)).toEqual({
      winner: 'BLUE',
      reason: 'GOAL',
    });
    expect(resultFor(map, { '0,0': 'B' }, 'BLUE', 1)?.reason).toBe('WIPEOUT');
    const blocked = {
      '0,4': 'b',
      '1,4': 'B',
      '1,3': 'B',
      '0,3': 'B',
      '-1,4': 'B',
      '-1,5': 'B',
      '0,5': 'B',
    } as const;
    expect(resultFor(map, blocked, 'BLUE', 1)?.reason).toBe('STALEMATE');
    expect(resultFor(map, initialPosition(map), 'RED', 300)).toEqual({ winner: 'RED', reason: 'MOVE_LIMIT' });
    for (const bot of ['greedy', 'hard'] as const) {
      const p = { '0,-4': 'B', '0,4': 'p' } as const;
      expect(chooseMove(map, p, 'BLUE', bot, 0).to).toBe(goals.BLUE);
    }
  },
);

it.each(['hexagon', 'ring', 'circular'] as const)(
  '%s bots play a complete legal game without a server',
  (map) => {
    const fetch = vi.fn();
    vi.stubGlobal('fetch', fetch);
    let g = newSpecial(map, 'RED', 'greedy');
    while (!frame(g).result) {
      const f = frame(g);
      g = playSpecial(g, chooseMove(map, f.position, g.human, 'greedy', g.moves.length));
    }
    expect(g.moves.length).toBeLessThanOrEqual(300);
    expect(parseSpecial(JSON.stringify(g))).toEqual(g);
    expect(fetch).not.toHaveBeenCalled();
  },
);

it('circular board has 96 cells, rotationally symmetric armies and empty goals', () => {
  expect(cells('circular')).toHaveLength(96);
  const p = initialPosition('circular');
  for (const kind of ['B', 'P', 'K', 'b', 'p', 'k'])
    expect(Object.values(p).filter((v) => v === kind)).toHaveLength(4);
  for (const c of cells('circular'))
    if (p[c.id]) expect(p[`${(c.q + 12) % 24},${c.r}`]?.toUpperCase()).toBe(p[c.id].toUpperCase());
  expect(p['0,3']).toBeUndefined();
  expect(p['12,3']).toBeUndefined();
  expect(resultFor('circular', p, 'RED', 300)).toEqual({ winner: 'RED', reason: 'MOVE_LIMIT' });
});

it('circular adjacency wraps at the seam in both directions but not across the hole or rim', () => {
  const moves = movesFor('circular', { '0,1': 'B' }, 'BLUE');
  expect(moves).toHaveLength(8);
  expect(moves.map((m) => m.to)).toEqual(
    expect.arrayContaining(['23,0', '23,1', '23,2', '1,0', '1,1', '1,2', '0,0', '0,2']),
  );
  expect(movesFor('circular', { '23,1': 'B' }, 'BLUE').map((m) => m.to)).toContain('0,1');
  for (const row of [0, 3]) {
    const edge = movesFor('circular', { [`5,${row}`]: 'B' }, 'BLUE');
    expect(edge).toHaveLength(5);
    expect(edge.every((m) => cells('circular').some((c) => c.id === m.to))).toBe(true);
  }
  const capture = movesFor('circular', { '0,1': 'B', '23,1': 'k', '1,1': 'p', '0,0': 'b' }, 'BLUE');
  expect(capture.map((m) => m.to)).toContain('23,1');
  expect(capture.map((m) => m.to)).not.toContain('1,1');
  expect(capture.map((m) => m.to)).not.toContain('0,0');
  for (const bot of ['greedy', 'hard'] as const)
    expect(chooseMove('circular', { '23,3': 'B', '10,0': 'p' }, 'BLUE', bot, 0).to).toBe('0,3');
});

it('circular cells support keyboard selection and keep the center noninteractive', () => {
  const click = vi.fn();
  render(<SpecialBoard map="circular" position={initialPosition('circular')} onCell={click} />);
  expect(screen.getAllByRole('button')).toHaveLength(96);
  fireEvent.keyDown(screen.getByRole('button', { name: /^Ô 12,0:/ }), { key: 'Enter' });
  expect(click).toHaveBeenCalledWith('12,0');
});

it('hard stops an immediate enemy goal threat', () => {
  const p = { '0,3': 'B', '0,4': 'k', '3,-2': 'B', '3,-3': 'k', '-3,0': 'p' } as const;
  const move = chooseMove('hexagon', p, 'BLUE', 'hard', 0);
  const after = moved(p, move);
  expect(
    movesFor('hexagon', after, 'RED').some(
      (m) => resultFor('hexagon', moved(after, m), 'RED', 2)?.winner === 'RED',
    ),
  ).toBe(false);
});

it('validates history, separates accounts and rejects stale writes', async () => {
  const g = newSpecial('ring', 'BLUE', 'hard');
  await storeSpecial(user.id, g);
  expect(readSpecial(user.id, g.id)).toEqual(g);
  expect(listSpecial('someone-else')).toEqual([]);
  expect(localStorage.getItem(`ottv2.casual.v1:${user.id}`)).toBeNull();
  expect(parseSpecial(JSON.stringify({ ...g, version: 'other' }))).toBeNull();
  expect(parseSpecial(JSON.stringify({ ...g, moves: [{ from: '0,3', to: '0,-5' }] }))).toBeNull();
  await storeSpecial(user.id, { ...g, resigned: true }, g);
  await expect(storeSpecial(user.id, g, g)).rejects.toThrow('tab khác');
});

it('exposes a separate mode and creates the chosen ring map with a bot opening', async () => {
  render(
    <MemoryRouter initialEntries={['/special']}>
      <Routes>
        <Route path="/special" element={<SpecialLobby user={user} />} />
        <Route path="/special/:id" element={<SpecialPlay user={user} />} />
      </Routes>
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole('button', { name: /Vành khuyên 96 ô/ }));
  fireEvent.change(screen.getByLabelText('Màu quân'), { target: { value: 'RED' } });
  fireEvent.change(screen.getByLabelText('Độ khó'), { target: { value: 'hard' } });
  fireEvent.click(screen.getByRole('button', { name: 'Chơi Vành khuyên' }));
  await screen.findByText('Lượt của bạn · Chọn quân rồi chọn ô sáng');
  expect(listSpecial(user.id)[0]).toMatchObject({ map: 'circular', human: 'RED', bot: 'hard' });
  expect(listSpecial(user.id)[0].moves).toHaveLength(1);
});

it('supports a move, read-only review, resignation and rematch with the same settings', async () => {
  const g = newSpecial('hexagon', 'BLUE', 'random');
  await storeSpecial(user.id, g);
  render(
    <MemoryRouter initialEntries={[`/special/${g.id}`]}>
      <Routes>
        <Route path="/special/:id" element={<SpecialPlay user={user} />} />
      </Routes>
    </MemoryRouter>,
  );
  const move = movesFor(g.map, initialPosition(g.map), 'BLUE')[0];
  fireEvent.click(screen.getByRole('button', { name: new RegExp(`^Ô ${move.from}:`) }));
  fireEvent.click(screen.getByRole('button', { name: new RegExp(`^Ô ${move.to}:`) }));
  await screen.findByText('Lịch sử · 2 nước');
  fireEvent.change(screen.getByLabelText('Nước xem lại'), { target: { value: '0' } });
  fireEvent.click(screen.getByRole('button', { name: new RegExp(`^Ô ${move.from}:`) }));
  fireEvent.click(screen.getByRole('button', { name: new RegExp(`^Ô ${move.to}:`) }));
  expect(readSpecial(user.id, g.id)?.moves).toHaveLength(2);
  fireEvent.click(screen.getByText('Về nước hiện tại'));
  fireEvent.click(screen.getByText('Đầu hàng'));
  fireEvent.click(screen.getByText('Xác nhận đầu hàng'));
  await screen.findByText('Ván đã kết thúc');
  expect(readSpecial(user.id, g.id)?.resigned).toBe(true);
  fireEvent.click(screen.getByText('Chơi lại'));
  await screen.findByText('Lịch sử · 0 nước');
  expect(listSpecial(user.id)[0]).toMatchObject({ map: g.map, bot: g.bot, human: g.human, resigned: false });
});

it('renders only playable cells and links special mode separately from Casual and Arena', () => {
  const view = render(<SpecialBoard map="ring" position={{}} onCell={() => {}} />);
  expect(screen.getAllByRole('button')).toHaveLength(84);
  expect(screen.queryByRole('button', { name: /^Ô 0,0:/ })).toBeNull();
  view.unmount();
  render(
    <MemoryRouter>
      <Modes />
    </MemoryRouter>,
  );
  expect(screen.getByText('Khám phá bản đồ →').getAttribute('href')).toBe('/special');
  expect(screen.getByText('Vào Arena →').getAttribute('href')).toBe('/arena');
});
