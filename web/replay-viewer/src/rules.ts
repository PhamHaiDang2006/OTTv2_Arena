import type { Board, OutcomeReason, Piece, Side } from '../../../contracts/viewer-api';
// dev-v1 rules for browser play (Casual), mirroring engine/ottv2/board.py and rules.py. Cross-checked in
// web/tests/rules.test.ts against engine/fixtures/positions.json and outcomes.json; change both together.
export const INITIAL_FEN = '9/pbkpbkpbk/kpbkpbkpb/9/9/9/BPKBPKBPK/KBPKBPKBP/9';
export const MAX_TURNS = 300;
export const GOAL: Record<Side, number> = { BLUE: 80, RED: 0 };
const CAPTURE: Record<string, string> = { B: 'K', K: 'P', P: 'B' };
const NEIGHBORS = Array.from({ length: 81 }, (_, i) => {
  const row = Math.floor(i / 9),
    col = i % 9,
    result: number[] = [];
  for (let y = Math.max(0, row - 1); y <= Math.min(8, row + 1); y++)
    for (let x = Math.max(0, col - 1); x <= Math.min(8, col + 1); x++)
      if (y * 9 + x !== i) result.push(y * 9 + x);
  return result;
});
export const other = (side: Side): Side => (side === 'BLUE' ? 'RED' : 'BLUE');
export const ownerOf = (piece: Piece): Side => (piece === piece.toUpperCase() ? 'BLUE' : 'RED');
export const squareName = (index: number) =>
  String.fromCharCode(97 + (index % 9)) + (Math.floor(index / 9) + 1);
function check(board: Board) {
  if (board.length !== 81) throw new Error('Bàn cờ phải có 81 ô.');
}
export function legalMoves(board: Board, side: Side): string[] {
  check(board);
  const forbidden = GOAL[other(side)],
    result: string[] = [];
  board.forEach((piece, from) => {
    if (!piece || ownerOf(piece) !== side) return;
    for (const to of NEIGHBORS[from]) {
      const target = board[to];
      if (to === forbidden) continue;
      if (!target || (ownerOf(target) !== side && CAPTURE[piece.toUpperCase()] === target.toUpperCase()))
        result.push(squareName(from) + squareName(to));
    }
  });
  return result;
}
export function isLegal(board: Board, move: string, side: Side) {
  return /^[a-i][1-9][a-i][1-9]$/.test(move) && legalMoves(board, side).includes(move);
}
function score(board: Board, side: Side): number[] {
  const own = board.flatMap((piece, i) => (piece && ownerOf(piece) === side ? [i] : []));
  const counts = ['B', 'P', 'K'].map((kind) => own.filter((i) => board[i]!.toUpperCase() === kind).length);
  const goal = GOAL[side];
  const distance = Math.min(
    9,
    ...own.map((i) =>
      Math.max(Math.abs((i % 9) - (goal % 9)), Math.abs(Math.floor(i / 9) - Math.floor(goal / 9))),
    ),
  );
  return [Math.min(...counts), own.length, -distance];
}
/** RULE-05: thinnest piece kind, then total pieces, then distance to goal; RED wins a full tie. */
export function tiebreak(board: Board): Side {
  const blue = score(board, 'BLUE'),
    red = score(board, 'RED');
  const first = blue.findIndex((value, i) => value !== red[i]);
  return first >= 0 && blue[first] > red[first] ? 'BLUE' : 'RED';
}
/** RULE-03/04 after a legal move by `mover`, `plies` counting that move: GOAL → WIPEOUT → STALEMATE → MOVE_LIMIT. */
export function outcome(
  board: Board,
  mover: Side,
  plies: number,
  maxTurns = MAX_TURNS,
): [Side, OutcomeReason] | null {
  check(board);
  const opponent = other(mover),
    goalPiece = board[GOAL[mover]];
  if (goalPiece && ownerOf(goalPiece) === mover) return [mover, 'GOAL'];
  if (!board.some((piece) => piece && ownerOf(piece) === opponent)) return [mover, 'WIPEOUT'];
  if (!legalMoves(board, opponent).length) return [mover, 'STALEMATE'];
  if (plies >= maxTurns) return [tiebreak(board), 'MOVE_LIMIT'];
  return null;
}
