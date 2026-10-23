import type { Replay, Side } from './generated/types';
export type { Side };
export type Piece = 'B' | 'P' | 'K' | 'b' | 'p' | 'k';
/** 81 cells, a1=0, i1=8, a9=72. Functions must validate length at runtime. */
export type Board = ReadonlyArray<Piece | null>;
export interface ReplayViewerProps {
  replay: Replay;
  mode: 'participant' | 'admin';
  stderr?: { BLUE: string; RED: string };
  onDownload?: () => void;
}
/** A implements these as exports of @ottv2/replay-viewer. */
export type ParseFen = (fen: string) => Board;
export type ApplyMove = (board: Board, move: string) => Board;
/** dev-v1 rules for browser play (Casual, contract 1.3.0), cross-checked with engine fixtures. */
export type OutcomeReason = 'GOAL' | 'WIPEOUT' | 'STALEMATE' | 'MOVE_LIMIT';
export type LegalMoves = (board: Board, side: Side) => string[];
/** Called after a legal move by `mover`; `plies` counts that move. Null while the game goes on. */
export type Outcome = (board: Board, mover: Side, plies: number, maxTurns?: number) => [Side, OutcomeReason] | null;
