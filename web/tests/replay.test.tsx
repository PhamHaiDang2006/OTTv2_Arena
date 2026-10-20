import { afterEach, describe, expect, it } from 'vitest';
import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { applyMove, parseFen, ReplayViewer, toFen } from '../replay-viewer/src';
import type { Replay } from '../../contracts/generated/types';
import manifest from '../../engine/fixtures/manifest.json';
import positions from '../../engine/fixtures/positions.json';
import boardCases from '../../contracts/fixtures/board-cases.json';
const fixture = (name: string): Replay =>
  JSON.parse(readFileSync(resolve('../engine/fixtures', name), 'utf8'));
const generatedPath = resolve('tests/generated/engine-replays.json');
afterEach(cleanup);
describe('engine / browser board contract', () => {
  it('seeks a 600-ply synthetic performance fixture without mutating it', () => {
    // Performance-only timeline, not a claim that dev-v1 allows games longer than max_turns.
    const base = fixture('move-limit.json');
    const moves: Replay['moves'] = Array.from({ length: 600 }, (_, i) => ({
      ply: i + 1,
      side: i % 2 === 0 ? 'BLUE' : 'RED',
      move: ['b2c2', 'h8g8', 'c2b2', 'g8h8'][i % 4],
      think_ms: 1,
      clock_ms: 60000 - i,
      capture: null,
      debug: [],
    }));
    const data: Replay = { ...base, moves, result: { ...base.result, plies: 600 } };
    const before = JSON.stringify(data),
      started = performance.now();
    render(<ReplayViewer replay={data} mode="participant" />);
    fireEvent.click(screen.getByLabelText('Về cuối'));
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('600');
    fireEvent.click(screen.getByLabelText('Về đầu'));
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('0');
    expect(JSON.stringify(data)).toBe(before);
    expect(performance.now() - started).toBeLessThan(5000);
  });
  it.skipIf(!existsSync(generatedPath))('matches final FEN of 100 actual engine games', () => {
    const cases: { replay: Replay; expected_final_fen: string }[] = JSON.parse(
      readFileSync(generatedPath, 'utf8'),
    );
    expect(cases).toHaveLength(100);
    for (const item of cases) {
      const final = item.replay.moves.reduce(
        (board, move) => applyMove(board, move.move),
        parseFen(item.replay.initial_fen),
      );
      expect(toFen(final)).toBe(item.expected_final_fen);
    }
  });
  it('round trips 1000 engine positions', () => {
    for (const position of positions.cases) expect(toFen(parseFen(position.fen))).toBe(position.fen);
  });
  for (const item of manifest.cases)
    it(`replays engine ${item.file} to expected final FEN without mutation`, () => {
      const replay = fixture(item.file),
        before = JSON.stringify(replay);
      const final = replay.moves.reduce(
        (board, move) => applyMove(board, move.move),
        parseFen(replay.initial_fen),
      );
      expect(toFen(final)).toBe(item.expected_final_fen);
      expect(JSON.stringify(replay)).toBe(before);
    });
  for (const item of boardCases.cases.filter((c) => c.legal))
    it(`board contract ${item.id}`, () => {
      const board = parseFen(item.initial_fen),
        before = [...board];
      expect(toFen(applyMove(board, item.move))).toBe(item.expected_fen);
      expect(board).toEqual(before);
    });
  it('rejects malformed board/FEN/move', () => {
    expect(() => parseFen('9/9')).toThrow();
    expect(() => parseFen('9/9/9/9/9/9/9/9/x8')).toThrow();
    expect(() => applyMove([], 'a1a2')).toThrow();
    expect(() => applyMove(parseFen('9/9/9/9/9/9/9/9/9'), 'a1a2')).toThrow();
  });
  it('seeks back after capture and hides admin stderr from participant', () => {
    render(
      <ReplayViewer
        replay={fixture('capture.json')}
        mode="participant"
        stderr={{ BLUE: 'PRIVATE_SECRET', RED: 'PRIVATE_SECRET' }}
      />,
    );
    fireEvent.click(screen.getByLabelText('Về cuối'));
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('1');
    fireEvent.click(screen.getByLabelText('Về đầu'));
    expect(screen.getByRole('img').getAttribute('aria-label')).toContain('0');
    expect(screen.queryByText('PRIVATE_SECRET')).toBeNull();
  });
  it('handles zero-ply and invalid replays without crashing', () => {
    const { rerender } = render(<ReplayViewer replay={fixture('crash-zero-ply.json')} mode="participant" />);
    expect(screen.getByRole('img')).toBeTruthy();
    rerender(
      <ReplayViewer
        replay={{ ...fixture('capture.json'), format: 2 } as unknown as Replay}
        mode="participant"
      />,
    );
    expect(screen.getByRole('alert').textContent).toContain('Không đọc được replay');
  });
});
