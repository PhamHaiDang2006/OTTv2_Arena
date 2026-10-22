import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { INITIAL_FEN, applyMove, isLegal, legalMoves, outcome, parseFen, toFen } from '../replay-viewer/src';
import type { Replay } from '../../contracts/generated/types';
import positions from '../../engine/fixtures/positions.json';
import outcomes from '../../engine/fixtures/outcomes.json';
import boardCases from '../../contracts/fixtures/board-cases.json';
const generatedPath = resolve('tests/generated/engine-replays.json');
type Side = 'BLUE' | 'RED';
describe('browser dev-v1 rules match the Python engine', () => {
  it('generates the same legal moves for 1000 engine positions', () => {
    for (const position of positions.cases) {
      const board = parseFen(position.fen);
      expect(legalMoves(board, 'BLUE').sort()).toEqual(position.BLUE);
      expect(legalMoves(board, 'RED').sort()).toEqual(position.RED);
    }
  });
  it('agrees with every shared board case', () => {
    for (const item of boardCases.cases) {
      const board = parseFen(item.initial_fen);
      expect(isLegal(board, item.move, item.side as Side)).toBe(item.legal);
      if (item.legal) expect(toFen(applyMove(board, item.move))).toBe(item.expected_fen);
    }
  });
  it('decides 600 engine outcomes, including tiebreaks at the move limit', () => {
    const reasons = new Set<string>();
    for (const item of outcomes.cases) {
      expect(outcome(parseFen(item.fen), item.mover as Side, item.plies, outcomes.max_turns)).toEqual(
        item.outcome,
      );
      if (item.outcome) reasons.add(item.outcome[1] as string);
    }
    expect([...reasons].sort()).toEqual(['GOAL', 'MOVE_LIMIT', 'STALEMATE', 'WIPEOUT']);
  });
  it('starts from the standard position with Blue to move', () => {
    expect(legalMoves(parseFen(INITIAL_FEN), 'BLUE').length).toBeGreaterThan(0);
    expect(isLegal(parseFen(INITIAL_FEN), 'c7c6', 'BLUE')).toBe(false);
  });
  it.skipIf(!existsSync(generatedPath))('replays 100 actual engine games move by move', () => {
    const cases: { replay: Replay }[] = JSON.parse(readFileSync(generatedPath, 'utf8'));
    for (const { replay } of cases) {
      let board = parseFen(replay.initial_fen);
      replay.moves.forEach((move, index) => {
        expect(isLegal(board, move.move, move.side)).toBe(true);
        board = applyMove(board, move.move);
        const result = outcome(board, move.side, index + 1);
        if (index + 1 < replay.moves.length) expect(result).toBeNull();
        else expect(result).toEqual([replay.result.winner, replay.result.reason]);
      });
    }
  });
});
