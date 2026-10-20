import type { Board, Piece } from '../../../contracts/viewer-api';
const pieces = 'BPKbpk';
export function parseFen(fen: string): Board {
  const ranks = fen.split('/');
  if (ranks.length !== 9) throw new Error('FEN phải có 9 hàng.');
  const board: (Piece | null)[] = [];
  for (const rank of ranks.reverse()) {
    const row: (Piece | null)[] = [];
    for (const char of rank) {
      if (/^[1-9]$/.test(char)) row.push(...Array<null>(Number(char)).fill(null));
      else if (pieces.includes(char)) row.push(char as Piece);
      else throw new Error('Quân cờ trong FEN không hợp lệ.');
    }
    if (row.length !== 9) throw new Error('Mỗi hàng FEN phải có 9 ô.');
    board.push(...row);
  }
  return board;
}
export function toFen(board: Board) {
  if (board.length !== 81) throw new Error('Bàn cờ phải có 81 ô.');
  return Array.from({ length: 9 }, (_, rank) => {
    let text = '',
      empty = 0;
    for (const piece of board.slice((8 - rank) * 9, (9 - rank) * 9)) {
      if (piece === null) empty++;
      else {
        if (empty) text += empty;
        empty = 0;
        text += piece;
      }
    }
    return text + (empty || '');
  }).join('/');
}
export function squareIndex(square: string) {
  return (Number(square[1]) - 1) * 9 + square.charCodeAt(0) - 97;
}
export function applyMove(board: Board, move: string): Board {
  if (board.length !== 81 || board.some((p) => p !== null && !pieces.includes(p)))
    throw new Error('Bàn cờ không hợp lệ.');
  if (!/^[a-i][1-9][a-i][1-9]$/.test(move)) throw new Error('Nước đi không hợp lệ.');
  const from = squareIndex(move.slice(0, 2)),
    to = squareIndex(move.slice(2));
  if (!board[from] || from === to) throw new Error('Ô nguồn không có quân hoặc trùng ô đích.');
  const copy = [...board];
  copy[to] = copy[from];
  copy[from] = null;
  return copy;
}
