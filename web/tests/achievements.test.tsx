import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { act, cleanup, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { Achievements } from '../src/achievements';
import {
  difficulties,
  mapCells,
  readTraining,
  recordTraining,
  trainingAwards,
  trainingMaps,
} from '../src/training-progress';
import { collectCasualTraining, newGame, playMove, saveGame } from '../src/casual-engine';
import { collectSpecialTraining, type SpecialGame } from '../src/special-engine';
import vectors from '../../contracts/fixtures/room-games.json';

beforeEach(() => localStorage.clear());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

it('unions repeated cell visits and victories without mixing accounts or maps', () => {
  recordTraining('alice', 'standard', ['a1', 'a1', 'invalid'], 'random');
  recordTraining('alice', 'standard', ['b2'], 'random');
  recordTraining('alice', 'hexagon', ['0,0'], 'hard');
  expect(readTraining('alice').standard).toEqual({ visited: ['a1', 'b2'], wins: ['random'] });
  expect(readTraining('bob').standard.visited).toEqual([]);
  expect(readTraining('alice').circular.wins).toEqual([]);
});

it('unlocks exactly seven awards at all cells and all nine difficulty milestones', () => {
  expect(trainingMaps.map((m) => mapCells(m).length)).toEqual([81, 91, 96]);
  expect(trainingAwards(readTraining('a')).filter((a) => a.value === a.total)).toHaveLength(0);
  for (const map of trainingMaps)
    for (const bot of difficulties) recordTraining('a', map, mapCells(map), bot);
  expect(trainingAwards(readTraining('a')).filter((a) => a.value === a.total)).toHaveLength(7);
  expect(trainingAwards(readTraining('a')).at(-1)?.value).toBe(9);
});

it('records only human destinations and survives history removal', () => {
  const initial = newGame('RED', 'random', () => 0);
  saveGame('a', initial);
  expect(readTraining('a').standard.visited).toEqual([]);
  const game = playMove(initial, initial.legal_moves[0], () => 0);
  saveGame('a', game);
  expect(readTraining('a').standard.visited).toEqual([game.moves[1].move.slice(2)]);
  localStorage.removeItem('ottv2.casual.v1:a');
  collectCasualTraining('a', game);
  expect(readTraining('a').standard.visited).toHaveLength(1);
});

it('does not trust cached winners or illegal casual histories', () => {
  const game = newGame('BLUE', 'random');
  collectCasualTraining('a', { ...game, winner: 'BLUE', status: 'finished', reason: 'GOAL' });
  collectCasualTraining('a', {
    ...game,
    ply: 1,
    moves: [{ side: 'BLUE', move: 'a1i9', capture: null }],
  } as typeof game);
  expect(readTraining('a').standard).toEqual({ visited: [], wins: [] });
});

it.each(vectors)('derives $map victories from complete legal histories', (vector) => {
  const game = {
    version: 'special-v1',
    id: 'a'.repeat(32),
    map: vector.map,
    human: vector.result.winner,
    bot: 'hard',
    moves: vector.moves,
    resigned: false,
    created: '2026-10-26T00:00:00Z',
  } as SpecialGame;
  collectSpecialTraining('winner', game);
  collectSpecialTraining('winner', game);
  collectSpecialTraining('loser', { ...game, human: game.human === 'BLUE' ? 'RED' : 'BLUE' });
  const map = game.map as 'hexagon' | 'circular';
  expect(readTraining('winner')[map].wins).toEqual(['hard']);
  expect(readTraining('loser')[map].wins).toEqual([]);
  collectSpecialTraining('resigned', { ...game, resigned: true });
  expect(readTraining('resigned')[map].wins).toEqual([]);
});

it('shows progress immediately when another game records a milestone', () => {
  render(
    <MemoryRouter>
      <Achievements userId="a" />
    </MemoryRouter>,
  );
  expect(screen.getByRole('status').textContent).toContain('0/7');
  act(() => recordTraining('a', 'hexagon', mapCells('hexagon'), 'hard'));
  expect(screen.getByRole('status').textContent).toContain('1/7');
  expect(screen.getByText('✓ Đã thắng')).toBeTruthy();
  expect(screen.getAllByRole('progressbar')).toHaveLength(7);
});

it('keeps a visible warning when history backfill cannot be stored', () => {
  const game = newGame('BLUE', 'random');
  saveGame(
    'a',
    playMove(game, game.legal_moves[0], () => 0),
  );
  for (const key of Object.keys(localStorage))
    if (key.startsWith('ottv2.training.')) localStorage.removeItem(key);
  vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
    throw new Error('quota');
  });
  render(
    <MemoryRouter>
      <Achievements userId="a" />
    </MemoryRouter>,
  );
  expect(screen.getByText(/Không đọc được toàn bộ lịch sử/)).toBeTruthy();
});
