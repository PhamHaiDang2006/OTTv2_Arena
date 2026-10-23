import {
  INITIAL_FEN,
  MAX_TURNS,
  applyMove,
  legalMoves,
  other,
  outcome,
  parseFen,
  toFen,
} from '@ottv2/replay-viewer';
import type { Piece, Side } from '../../contracts/viewer-api';
// Casual runs entirely in the browser (contract 1.3.0): rules from @ottv2/replay-viewer, sample bots here,
// games saved per account in this browser's localStorage. Nothing is sent to the server.
export type CasualBot = 'random' | 'greedy' | 'hard';
export type CasualReason = 'GOAL' | 'WIPEOUT' | 'STALEMATE' | 'MOVE_LIMIT' | 'RESIGNED';
export interface CasualGame {
  id: string;
  fen: string;
  human_side: Side;
  bot: CasualBot;
  status: 'playing' | 'finished';
  ply: number;
  turn: Side | null;
  legal_moves: string[];
  moves: { side: Side; move: string; capture: Piece | null }[];
  winner: Side | null;
  reason: CasualReason | null;
  created_at: string;
}
export type Random = () => number;
export const MAX_SAVED_GAMES = 50;
function advance(game: CasualGame, move: string): CasualGame {
  const mover = game.turn!;
  if (!game.legal_moves.includes(move)) throw new Error('Nước đi không hợp lệ.');
  const board = parseFen(game.fen),
    capture = board[(Number(move[3]) - 1) * 9 + move.charCodeAt(2) - 97];
  const next = applyMove(board, move),
    ply = game.ply + 1;
  const base = { ...game, fen: toFen(next), ply, moves: [...game.moves, { side: mover, move, capture }] };
  const result = outcome(next, mover, ply, MAX_TURNS);
  if (result)
    return { ...base, status: 'finished', turn: null, legal_moves: [], winner: result[0], reason: result[1] };
  const turn = other(mover);
  return { ...base, turn, legal_moves: legalMoves(next, turn) };
}
/** Random: a shuffled legal move. Greedy: win now, else capture, else get closest to the goal. */
export function botMove(game: CasualGame, random: Random = Math.random): string {
  const side = game.turn!,
    moves = [...game.legal_moves];
  for (let i = moves.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [moves[i], moves[j]] = [moves[j], moves[i]];
  }
  if (game.bot === 'random') return moves[0];
  const board = parseFen(game.fen),
    goal = side === 'BLUE' ? 80 : 0;
  if (game.bot === 'hard') {
    // Two plies: consider every opponent reply, pruning replies once a move cannot beat best.
    // No beam truncation: even a quiet goal threat must be considered.
    const evaluate = (position: ReturnType<typeof parseFen>) => {
      let value = 0;
      const closest = { BLUE: 9, RED: 9 };
      const counts = { BLUE: [0, 0, 0], RED: [0, 0, 0] };
      position.forEach((piece, index) => {
        if (!piece) return;
        const owner: Side = piece === piece.toUpperCase() ? 'BLUE' : 'RED';
        const target = owner === 'BLUE' ? 80 : 0;
        const distance = Math.max(
          Math.abs((index % 9) - (target % 9)),
          Math.abs(Math.floor(index / 9) - Math.floor(target / 9)),
        );
        closest[owner] = Math.min(closest[owner], distance);
        counts[owner]['BPK'.indexOf(piece.toUpperCase())]++;
        value += (owner === side ? 1 : -1) * (100 + (8 - distance) * 2);
      });
      return (
        value +
        12 * (closest[other(side)] - closest[side]) +
        20 * (Math.min(...counts[side]) - Math.min(...counts[other(side)]))
      );
    };
    let best = moves[0],
      bestValue = -Infinity;
    for (const move of moves) {
      const next = applyMove(board, move);
      const result = outcome(next, side, game.ply + 1, MAX_TURNS);
      let value: number;
      if (result) value = result[0] === side ? 100000 : -100000;
      else {
        value = Infinity;
        for (const reply of legalMoves(next, other(side))) {
          const after = applyMove(next, reply);
          const end = outcome(after, other(side), game.ply + 2, MAX_TURNS);
          value = Math.min(value, end ? (end[0] === side ? 100000 : -100000) : evaluate(after));
          if (value <= bestValue) break;
        }
      }
      if (value > bestValue) {
        best = move;
        bestValue = value;
      }
      if (bestValue === 100000) break;
    }
    return best;
  }
  const score = (move: string) => {
    const target = (Number(move[3]) - 1) * 9 + move.charCodeAt(2) - 97;
    const result = outcome(applyMove(board, move), side, game.ply + 1, MAX_TURNS);
    const distance = Math.max(
      Math.abs((target % 9) - (goal % 9)),
      Math.abs(Math.floor(target / 9) - Math.floor(goal / 9)),
    );
    return [result?.[0] === side ? 1 : 0, board[target] ? 1 : 0, -distance];
  };
  let best = moves[0],
    bestScore = score(best);
  for (const move of moves.slice(1)) {
    const value = score(move),
      first = value.findIndex((x, i) => x !== bestScore[i]);
    if (first >= 0 && value[first] > bestScore[first]) [best, bestScore] = [move, value];
  }
  return best;
}
function botTurn(game: CasualGame, random: Random) {
  return game.status === 'playing' && game.turn !== game.human_side
    ? advance(game, botMove(game, random))
    : game;
}
// randomUUID needs a secure context; getRandomValues also works on plain http.
const newId = () =>
  crypto.randomUUID?.() ??
  Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join('');
export function newGame(humanSide: Side, bot: CasualBot, random: Random = Math.random): CasualGame {
  const game: CasualGame = {
    id: newId(),
    fen: INITIAL_FEN,
    human_side: humanSide,
    bot,
    status: 'playing',
    ply: 0,
    turn: 'BLUE',
    legal_moves: legalMoves(parseFen(INITIAL_FEN), 'BLUE'),
    moves: [],
    winner: null,
    reason: null,
    created_at: new Date().toISOString(),
  };
  return botTurn(game, random);
}
/** The human move, then at most one bot reply, as the server did before 1.3.0. */
export function playMove(game: CasualGame, move: string, random: Random = Math.random): CasualGame {
  if (game.status !== 'playing' || game.turn !== game.human_side) throw new Error('Chưa đến lượt của bạn.');
  return botTurn(advance(game, move), random);
}
export function resign(game: CasualGame): CasualGame {
  if (game.status !== 'playing') throw new Error('Ván đã kết thúc.');
  return {
    ...game,
    status: 'finished',
    turn: null,
    legal_moves: [],
    winner: other(game.human_side),
    reason: 'RESIGNED',
  };
}
const storageKey = (userId: string) => `ottv2.casual.v1:${userId}`;
// Games the browser refused to store: kept for this page load so the current game can go on.
const unsaved = new Map<string, CasualGame[]>();
function isGame(value: unknown): value is CasualGame {
  const game = value as CasualGame;
  try {
    return (
      typeof game?.id === 'string' &&
      typeof game.created_at === 'string' &&
      ['BLUE', 'RED'].includes(game.human_side) &&
      ['random', 'greedy', 'hard'].includes(game.bot) &&
      ['playing', 'finished'].includes(game.status) &&
      Number.isInteger(game.ply) &&
      Array.isArray(game.moves) &&
      Array.isArray(game.legal_moves) &&
      parseFen(game.fen).length === 81
    );
  } catch {
    return false;
  }
}
function stored(userId: string): CasualGame[] {
  try {
    const data: unknown = JSON.parse(localStorage.getItem(storageKey(userId)) ?? '[]');
    return Array.isArray(data) ? data.filter(isGame) : [];
  } catch {
    return [];
  }
}
/** Newest first. */
export function loadGames(userId: string): CasualGame[] {
  const games = new Map(stored(userId).map((g) => [g.id, g]));
  for (const game of unsaved.get(userId) ?? [])
    if ((games.get(game.id)?.ply ?? -1) <= game.ply) games.set(game.id, game);
  return [...games.values()].sort((a, b) => b.created_at.localeCompare(a.created_at));
}
/** Keeps the most recent MAX_SAVED_GAMES. Throws if the browser refuses to store; the game stays playable.
 * Rewrites the whole list, so pages call it inside withGamesLock. */
export function saveGame(userId: string, game: CasualGame) {
  const games = [game, ...loadGames(userId).filter((g) => g.id !== game.id)]
    .sort((a, b) => b.created_at.localeCompare(a.created_at))
    .slice(0, MAX_SAVED_GAMES);
  try {
    localStorage.setItem(storageKey(userId), JSON.stringify(games));
    unsaved.delete(userId);
  } catch {
    unsaved.set(userId, games);
    throw new Error('Trình duyệt không cho lưu ván. Vẫn chơi tiếp được nhưng ván sẽ mất khi tải lại trang.');
  }
}
/** Runs `task` while holding this account's Web Lock, so tabs read, check and write the game list one at a
 * time. Browsers without Web Locks run it directly. */
export async function withGamesLock<T>(userId: string, task: () => T): Promise<T> {
  const locks = typeof navigator === 'undefined' ? undefined : navigator.locks;
  return locks ? locks.request(storageKey(userId), () => task()) : task();
}
/** Re-reads the game under the lock and refuses, instead of overwriting, when another tab changed it after
 * `shown` was displayed. */
export function updateGame(userId: string, shown: CasualGame, change: (game: CasualGame) => CasualGame) {
  return withGamesLock(userId, () => {
    const latest = loadGames(userId).find((g) => g.id === shown.id);
    if (latest && (latest.ply !== shown.ply || latest.status !== shown.status))
      throw new Error('Ván vừa thay đổi ở một tab khác. Bàn cờ đã được tải lại.');
    const next = change(shown);
    saveGame(userId, next);
    return next;
  });
}
export function isCasualStorageKey(key: string | null, userId: string) {
  return key === null || key === storageKey(userId);
}
