import type { Replay } from './generated/types';
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
