// Browser-only experimental rules. Never serialize these games as Arena Replay/FEN.
import { other, ownerOf } from '@ottv2/replay-viewer';
import type { Piece, Side } from '../../contracts/viewer-api';
import type { CasualBot } from './casual-engine';
import { recordTraining } from './training-progress';

export type MapId = 'hexagon' | 'ring' | 'circular';
export type Move = { from: string; to: string };
export type Position = Record<string, Piece>;
export const RULESET = 'special-v1' as const;
export const LIMIT = 300;
export const mapNames = { hexagon: 'Hexagon', ring: 'Annulus cũ (hex)', circular: 'Annulus' };
export const goals: Record<Side, string> = { BLUE: '0,-5', RED: '0,5' };
export const mapGoals = (map: MapId): Record<Side, string> =>
  map === 'circular' ? { BLUE: '0,3', RED: '12,3' } : goals;
const vectors = [
  [1, 0],
  [1, -1],
  [0, -1],
  [-1, 0],
  [-1, 1],
  [0, 1],
];
const capture: Record<string, string> = { B: 'K', K: 'P', P: 'B' };
export const key = (q: number, r: number) => `${q},${r}`;
export const cells = (map: MapId) => {
  const result: { id: string; q: number; r: number }[] = [];
  if (map === 'circular') {
    for (let q = 0; q < 24; q++) for (let r = 0; r < 4; r++) result.push({ id: key(q, r), q, r });
    return result;
  }
  for (let q = -5; q <= 5; q++)
    for (let r = -5; r <= 5; r++) {
      const radius = Math.max(Math.abs(q), Math.abs(r), Math.abs(q + r));
      if (radius <= 5 && (map !== 'ring' || radius > 1)) result.push({ id: key(q, r), q, r });
    }
  return result;
};
const maps = { hexagon: cells('hexagon'), ring: cells('ring'), circular: cells('circular') };
const adjacency = Object.fromEntries(
  Object.entries(maps).map(([map, list]) => {
    const ids = new Set(list.map((c) => c.id));
    return [
      map,
      Object.fromEntries(
        list.map((c) => [
          c.id,
          (map === 'circular'
            ? [
                [1, 0],
                [-1, 0],
                [0, 1],
                [0, -1],
                [1, 1],
                [1, -1],
                [-1, 1],
                [-1, -1],
              ]
            : vectors
          )
            .map(([q, r]) => key(map === 'circular' ? (c.q + q + 24) % 24 : c.q + q, c.r + r))
            .filter((id) => ids.has(id)),
        ]),
      ),
    ];
  }),
) as Record<MapId, Record<string, string[]>>;
// Graph distance accounts for the missing center of the ring.
const distances = Object.fromEntries(
  Object.entries(adjacency).map(([map, graph]) => [
    map,
    Object.fromEntries(
      (['BLUE', 'RED'] as const).map((side) => {
        const goals = mapGoals(map as MapId);
        const distance: Record<string, number> = { [goals[side]]: 0 },
          queue = [goals[side]];
        for (let i = 0; i < queue.length; i++)
          for (const next of graph[queue[i]]) {
            if (distance[next] !== undefined) continue;
            distance[next] = distance[queue[i]] + 1;
            queue.push(next);
          }
        return [side, distance];
      }),
    ),
  ]),
) as Record<MapId, Record<Side, Record<string, number>>>;

export function initialPosition(map: MapId): Position {
  const position: Position = {};
  if (map === 'circular') {
    const starting = maps.circular.filter((c) => c.q >= 11 && c.q <= 13 && c.id !== '12,3');
    starting.push({ id: '10,3', q: 10, r: 3 });
    starting.forEach((c, i) => {
      const piece = ['B', 'P', 'K'][i % 3] as Piece;
      position[c.id] = piece;
      position[key((c.q + 12) % 24, c.r)] = piece.toLowerCase() as Piece;
    });
    return position;
  }
  const starting = [...maps[map]]
    .filter((c) => c.id !== goals.RED)
    .sort((a, b) => b.r + b.q / 2 - (a.r + a.q / 2) || a.q - b.q)
    .slice(0, 12);
  starting.forEach((c, i) => {
    const piece = ['B', 'P', 'K'][i % 3] as Piece;
    position[c.id] = piece;
    position[key(-c.q, -c.r)] = piece.toLowerCase() as Piece;
  });
  return position;
}
export function movesFor(map: MapId, position: Position, side: Side): Move[] {
  return Object.entries(position).flatMap(([from, piece]) =>
    ownerOf(piece) !== side
      ? []
      : (adjacency[map][from] ?? [])
          .filter(
            (to) =>
              to !== mapGoals(map)[other(side)] &&
              (!position[to] ||
                (ownerOf(position[to]) !== side &&
                  capture[piece.toUpperCase()] === position[to].toUpperCase())),
          )
          .map((to) => ({ from, to })),
  );
}
export function moved(position: Position, move: Move): Position {
  const next = { ...position, [move.to]: position[move.from] };
  delete next[move.from];
  return next;
}
export type Result = { winner: Side; reason: 'GOAL' | 'WIPEOUT' | 'STALEMATE' | 'MOVE_LIMIT' | 'RESIGNED' };
function score(map: MapId, position: Position, side: Side) {
  const own = Object.entries(position).filter(([, p]) => ownerOf(p) === side);
  return [
    Math.min(...['B', 'P', 'K'].map((kind) => own.filter(([, p]) => p.toUpperCase() === kind).length)),
    own.length,
    -Math.min(99, ...own.map(([id]) => distances[map][side][id])),
  ];
}
export function resultFor(map: MapId, position: Position, mover: Side, ply: number): Result | null {
  const goals = mapGoals(map);
  if (position[goals[mover]] && ownerOf(position[goals[mover]]) === mover)
    return { winner: mover, reason: 'GOAL' };
  if (!Object.values(position).some((p) => ownerOf(p) === other(mover)))
    return { winner: mover, reason: 'WIPEOUT' };
  if (!movesFor(map, position, other(mover)).length) return { winner: mover, reason: 'STALEMATE' };
  if (ply >= LIMIT) {
    const a = score(map, position, 'BLUE'),
      b = score(map, position, 'RED');
    const first = a.findIndex((v, i) => v !== b[i]);
    return { winner: first >= 0 && a[first] > b[first] ? 'BLUE' : 'RED', reason: 'MOVE_LIMIT' };
  }
  return null;
}
function evaluation(map: MapId, position: Position, side: Side) {
  const a = score(map, position, side),
    b = score(map, position, other(side));
  return 20 * (a[0] - b[0]) + 100 * (a[1] - b[1]) + 12 * (a[2] - b[2]);
}
export function chooseMove(
  map: MapId,
  position: Position,
  side: Side,
  bot: CasualBot,
  ply: number,
  random = Math.random,
): Move {
  const choices = movesFor(map, position, side);
  if (!choices.length) throw new Error('Không còn nước đi.');
  for (let i = choices.length - 1; i > 0; i--) {
    const j = Math.floor(random() * (i + 1));
    [choices[i], choices[j]] = [choices[j], choices[i]];
  }
  if (bot === 'random') return choices[0];
  let best = choices[0],
    value = -Infinity;
  for (const move of choices) {
    const next = moved(position, move),
      end = resultFor(map, next, side, ply + 1);
    let current = end
      ? end.winner === side
        ? 100000
        : -100000
      : (position[move.to] ? 100 : 0) - distances[map][side][move.to];
    if (!end && bot === 'hard') {
      current = Infinity;
      for (const reply of movesFor(map, next, other(side))) {
        const after = moved(next, reply),
          outcome = resultFor(map, after, other(side), ply + 2);
        current = Math.min(
          current,
          outcome ? (outcome.winner === side ? 100000 : -100000) : evaluation(map, after, side),
        );
        if (current <= value) break;
      }
    }
    if (current > value) {
      best = move;
      value = current;
    }
    if (value === 100000) break;
  }
  return best;
}
export interface SpecialGame {
  version: typeof RULESET;
  id: string;
  map: MapId;
  human: Side;
  bot: CasualBot;
  moves: Move[];
  resigned: boolean;
  created: string;
}
export function frame(game: SpecialGame, count = game.moves.length) {
  let position = initialPosition(game.map),
    turn: Side = 'BLUE',
    result: Result | null = null;
  for (const move of game.moves.slice(0, count)) {
    position = moved(position, move);
    turn = other(turn);
  }
  if (count) result = resultFor(game.map, position, other(turn), count);
  if (game.resigned && count === game.moves.length)
    result = { winner: other(game.human), reason: 'RESIGNED' };
  return { position, turn, result };
}
export function newSpecial(map: MapId, human: Side, bot: CasualBot): SpecialGame {
  const game: SpecialGame = {
    version: RULESET,
    id: Array.from(crypto.getRandomValues(new Uint8Array(16)), (b) => b.toString(16).padStart(2, '0')).join(
      '',
    ),
    map,
    human,
    bot,
    moves: [],
    resigned: false,
    created: new Date().toISOString(),
  };
  if (human === 'RED') game.moves.push(chooseMove(map, initialPosition(map), 'BLUE', bot, 0));
  return game;
}
export function playSpecial(game: SpecialGame, move: Move): SpecialGame {
  const { position, turn, result } = frame(game);
  if (
    result ||
    turn !== game.human ||
    !movesFor(game.map, position, turn).some((m) => m.from === move.from && m.to === move.to)
  )
    throw new Error('Nước đi không hợp lệ.');
  const moves = [...game.moves, move],
    next = moved(position, move);
  if (!resultFor(game.map, next, turn, moves.length))
    moves.push(chooseMove(game.map, next, other(turn), game.bot, moves.length));
  return { ...game, moves };
}
// Validate saved history by replaying legal moves; never trust cached board state.
export function parseSpecial(raw: string | null): SpecialGame | null {
  try {
    const g = JSON.parse(raw ?? 'null') as SpecialGame;
    if (
      !g ||
      g.version !== RULESET ||
      !/^[a-f0-9]{32}$/.test(g.id) ||
      !['hexagon', 'ring', 'circular'].includes(g.map) ||
      !['BLUE', 'RED'].includes(g.human) ||
      !['random', 'greedy', 'hard'].includes(g.bot) ||
      typeof g.resigned !== 'boolean' ||
      typeof g.created !== 'string' ||
      !Number.isFinite(Date.parse(g.created)) ||
      !Array.isArray(g.moves) ||
      g.moves.length > LIMIT
    )
      return null;
    let p = initialPosition(g.map),
      side: Side = 'BLUE';
    for (let i = 0; i < g.moves.length; i++) {
      const m = g.moves[i];
      if (!m || !movesFor(g.map, p, side).some((v) => v.from === m.from && v.to === m.to)) return null;
      p = moved(p, m);
      if (resultFor(g.map, p, side, i + 1) && (i !== g.moves.length - 1 || g.resigned)) return null;
      side = other(side);
    }
    if (!resultFor(g.map, p, other(side), g.moves.length) && side !== g.human) return null;
    return g;
  } catch {
    return null;
  }
}
export const specialKey = (user: string, id: string) => `ottv2.special.v1:${user}:${id}`;
export function readSpecial(user: string, id: string) {
  return parseSpecial(localStorage.getItem(specialKey(user, id)));
}
export function listSpecial(user: string): SpecialGame[] {
  const prefix = specialKey(user, '');
  return Object.keys(localStorage)
    .filter((k) => k.startsWith(prefix))
    .flatMap((k) => {
      const g = parseSpecial(localStorage.getItem(k));
      return g ? [g] : [];
    })
    .sort((a, b) => b.created.localeCompare(a.created));
}
export async function storeSpecial(user: string, game: SpecialGame, previous?: SpecialGame) {
  const name = specialKey(user, game.id);
  const write = () => {
    if (previous && localStorage.getItem(name) !== JSON.stringify(previous))
      throw new Error('Ván đã thay đổi ở tab khác. Hãy tải lại trang.');
    localStorage.setItem(name, JSON.stringify(game));
  };
  if (navigator.locks) await navigator.locks.request(name, write);
  else write();
  try {
    collectSpecialTraining(user, game);
  } catch {
    /* Retry collection from saved history on the achievements page. */
  }
}
export function collectSpecialTraining(user: string, game: SpecialGame) {
  if (game.map === 'ring' || !parseSpecial(JSON.stringify(game))) return;
  const result = frame(game).result;
  recordTraining(
    user,
    game.map,
    game.moves.filter((_, i) => (i % 2 ? 'RED' : 'BLUE') === game.human).map((m) => m.to),
    !game.resigned && result?.winner === game.human ? game.bot : undefined,
  );
}
