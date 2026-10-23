import { useEffect, useRef, type CSSProperties } from 'react';
import { applyMove, INITIAL_FEN, parseFen, toFen } from '@ottv2/replay-viewer';
import type { CasualGame } from './casual-engine';

export function Crest({ kind = 'goal' }: { kind?: 'goal' | 'bot' | 'player' | 'trophy' }) {
  return (
    <svg className="crest-icon" viewBox="0 0 64 64" fill="none" aria-hidden="true">
      {kind === 'bot' ? (
        <>
          <path
            d="M32 9v9M27 9h10M14 25l6-7h24l6 7v25H14zM8 31v12M56 31v12"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinejoin="round"
          />
          <rect x="22" y="28" width="6" height="8" rx="3" fill="currentColor" />
          <rect x="36" y="28" width="6" height="8" rx="3" fill="currentColor" />
          <path d="M25 43h14" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
        </>
      ) : kind === 'player' ? (
        <>
          <circle cx="32" cy="23" r="10" stroke="currentColor" strokeWidth="3" />
          <path
            d="M13 52c0-12 7-18 19-18s19 6 19 18M20 52h24"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinecap="round"
          />
        </>
      ) : kind === 'trophy' ? (
        <>
          <path
            d="M20 12h24v17c0 9-5 14-12 14s-12-5-12-14zM20 17H10v8c0 8 6 10 12 10M44 17h10v8c0 8-6 10-12 10M32 43v10M21 55h22"
            stroke="currentColor"
            strokeWidth="3"
            strokeLinejoin="round"
          />
          <path d="m32 19 3 6 7 1-5 5 1 7-6-3-6 3 1-7-5-5 7-1z" fill="currentColor" />
        </>
      ) : (
        <>
          <path d="m32 5 22 12v20L32 59 10 37V17z" stroke="currentColor" strokeWidth="2" />
          <path d="m32 17 4 9 10 1-8 7 2 11-8-5-8 5 2-11-8-7 10-1z" fill="currentColor" />
        </>
      )}
    </svg>
  );
}

export function MiniBoard({ fen }: { fen: string }) {
  const board = parseFen(fen);
  return (
    <div className="mini-board" aria-hidden="true">
      {Array.from({ length: 81 }, (_, i) => {
        const p = board[(8 - Math.floor(i / 9)) * 9 + (i % 9)];
        return (
          <i
            key={i}
            className={`${i % 2 ? 'alternate' : ''} ${p ? (p === p.toUpperCase() ? 'BLUE' : 'RED') : ''}`}
          >
            {p && <b />}
          </i>
        );
      })}
    </div>
  );
}

export function PieceIcon({ piece }: { piece: string }) {
  return (
    <svg className="piece-icon" viewBox="0 0 48 48" fill="none" aria-hidden="true" focusable="false">
      {piece.toUpperCase() === 'B' ? (
        <>
          <path d="m16 25 7 7-11 11-7-7z" fill="currentColor" />
          <path d="m13 13 9-9 19 19-9 9z" fill="currentColor" />
          <path
            d="m26 12 8 8M10 36l3 3"
            stroke="var(--piece-detail, white)"
            strokeWidth="2.5"
            strokeLinecap="round"
          />
        </>
      ) : piece.toUpperCase() === 'P' ? (
        <>
          <path d="M12 5h17l9 9v29H12z" fill="currentColor" />
          <path
            d="M29 5v10h9M19 23h12M19 29h12M19 35h8"
            stroke="var(--piece-detail, white)"
            strokeWidth="2.5"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        </>
      ) : (
        <>
          <circle cx="12" cy="35" r="7" stroke="currentColor" strokeWidth="4" />
          <circle cx="36" cy="35" r="7" stroke="currentColor" strokeWidth="4" />
          <path d="m17 30 20-25M31 30 11 5" stroke="currentColor" strokeWidth="5" strokeLinecap="round" />
          <circle cx="24" cy="21" r="2.5" fill="var(--piece-detail, white)" />
        </>
      )}
    </svg>
  );
}
/** Presentation-only history; never writes a replay frame back to the saved game. */
export function historyFrame(game: CasualGame, ply: number): CasualGame {
  let board = parseFen(INITIAL_FEN);
  for (const record of game.moves.slice(0, ply)) board = applyMove(board, record.move);
  return { ...game, fen: toFen(board), ply, moves: game.moves.slice(0, ply), legal_moves: [] };
}
export const resultReasons: Record<string, string> = {
  GOAL: 'Chiếm ô mục tiêu',
  WIPEOUT: 'Ăn hết quân',
  STALEMATE: 'Đối phương không còn nước đi',
  MOVE_LIMIT: 'Phân định sau 300 nước',
  RESIGNED: 'Bạn đã đầu hàng',
};
export function GameResult({
  game,
  onAgain,
  onReview,
  onLobby,
  busy,
  error,
}: {
  game: CasualGame;
  onAgain: () => void;
  onReview: () => void;
  onLobby: () => void;
  busy: boolean;
  error?: string;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const won = game.winner === game.human_side;
  useEffect(() => {
    const element = dialog.current!,
      previous = document.activeElement as HTMLElement | null;
    if (element.showModal) element.showModal();
    else element.setAttribute('open', '');
    element.querySelector<HTMLButtonElement>('button')?.focus();
    return () => {
      element.close?.();
      previous?.focus();
    };
  }, []);
  return (
    <dialog
      ref={dialog}
      className={`game-result ${won ? 'won' : 'lost'}`}
      aria-labelledby="result-title"
      aria-describedby="result-description"
      onCancel={(e) => {
        e.preventDefault();
        onReview();
      }}
    >
      {won && (
        <div className="confetti" aria-hidden="true">
          {Array.from({ length: 22 }, (_, i) => (
            <i
              key={i}
              style={
                {
                  '--i': i,
                  left: `${(i * 43) % 100}%`,
                  background: ['#d8b56c', '#70bc9b', '#6aa6ed'][i % 3],
                } as CSSProperties
              }
            />
          ))}
        </div>
      )}
      <div className="result-emblem" aria-hidden="true">
        <Crest kind={won ? 'trophy' : 'goal'} />
      </div>
      <p className="eyebrow">VÁN ĐẤU HOÀN TẤT</p>
      <h2 id="result-title">{won ? 'Chiến thắng!' : 'Một ván học hỏi'}</h2>
      <p id="result-description">
        {won ? 'Bạn đã thắng máy.' : 'Máy thắng ván này.'} {resultReasons[game.reason!]}
      </p>
      <div className="result-stats">
        <span>
          <strong>{game.ply}</strong> nước đi
        </span>
        <span>
          <strong>{game.moves.filter((m) => m.side === game.human_side && m.capture).length}</strong> quân bạn
          đã ăn
        </span>
      </div>
      <div className="result-actions">
        <button className="primary" disabled={busy} onClick={onAgain}>
          Chơi lại
        </button>
        <button disabled={busy} onClick={onReview}>
          Xem lại ván
        </button>
        <button disabled={busy} onClick={onLobby}>
          Về sảnh
        </button>
      </div>
      {error && (
        <p role="alert" className="error">
          {error}
        </p>
      )}
    </dialog>
  );
}
