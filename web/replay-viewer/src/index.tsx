import { useEffect, useMemo, useState } from 'react';
import type { ReplayViewerProps } from '../../../contracts/viewer-api';
import type { Replay } from '../../../contracts/generated/types';
import { applyMove, parseFen, squareIndex } from './board';
import { validate } from '../../shared/schema';
export { applyMove, parseFen, toFen } from './board';
export {
  INITIAL_FEN,
  MAX_TURNS,
  isLegal,
  legalMoves,
  other,
  outcome,
  ownerOf,
  squareName,
  tiebreak,
} from './rules';
const reasons: Record<string, string> = {
  GOAL: 'Chiếm ô mục tiêu',
  WIPEOUT: 'Ăn hết quân đối phương',
  STALEMATE: 'Đối phương không còn nước đi',
  TIMEOUT: 'Đối phương hết thời gian',
  ILLEGAL_MOVE: 'Đối phương đi không hợp lệ',
  CRASH: 'Bot đối phương dừng bất thường',
  MOVE_LIMIT: 'Đạt giới hạn nước đi',
};
export function ReplayViewer(props: ReplayViewerProps) {
  const [ply, setPly] = useState(0),
    [playing, setPlaying] = useState(false),
    [speed, setSpeed] = useState(500);
  const timeline = useMemo(() => {
    try {
      const replay = validate<Replay>('Replay', props.replay);
      if (replay.moves.length !== replay.result.plies) throw new Error('Số nước đi không khớp kết quả.');
      const boards = [parseFen(replay.initial_fen)];
      replay.moves.forEach((move, index) => {
        if (move.ply !== index + 1 || move.side !== (index % 2 === 0 ? 'BLUE' : 'RED'))
          throw new Error('Thứ tự nước đi không hợp lệ.');
        const before = boards[index],
          source = before[squareIndex(move.move.slice(0, 2))];
        if (
          !source ||
          (source === source.toUpperCase() ? 'BLUE' : 'RED') !== move.side ||
          before[squareIndex(move.move.slice(2))] !== move.capture
        )
          throw new Error('Nước đi không khớp bàn cờ.');
        boards.push(applyMove(before, move.move));
      });
      return { replay, boards, error: null };
    } catch (error) {
      return { replay: null, boards: [], error: String(error) };
    }
  }, [props.replay]);
  useEffect(() => {
    setPly(0);
    setPlaying(false);
  }, [props.replay]);
  useEffect(() => {
    if (!playing) return;
    const timer = setInterval(
      () =>
        setPly((current) => {
          if (current >= timeline.boards.length - 1) {
            setPlaying(false);
            return current;
          }
          return current + 1;
        }),
      speed,
    );
    return () => clearInterval(timer);
  }, [playing, speed, timeline.boards.length]);
  if (timeline.error || !timeline.replay) return <p role="alert">Không đọc được replay: {timeline.error}</p>;
  const { replay, boards } = timeline;
  const step = Math.min(ply, boards.length - 1),
    board = boards[step],
    move = replay.moves[step - 1];
  const jump = (index: number) => {
    setPlaying(false);
    setPly(Math.max(0, Math.min(index, replay.moves.length)));
  };
  const clocks = { BLUE: 60000, RED: 60000 };
  replay.moves.slice(0, step).forEach((m) => {
    clocks[m.side] = m.clock_ms;
  });
  return (
    <section
      className="replay"
      tabIndex={0}
      aria-label="Trình xem replay, dùng mũi tên để tua"
      onKeyDown={(e) => {
        if ((e.target as HTMLElement).matches('input, select, button, textarea')) return;
        if (e.key === 'ArrowLeft') {
          e.preventDefault();
          jump(step - 1);
        }
        if (e.key === 'ArrowRight') {
          e.preventDefault();
          jump(step + 1);
        }
        if (e.key === ' ') {
          e.preventDefault();
          setPlaying((v) => !v);
        }
      }}
    >
      <div>
        <div className="players">
          {(['BLUE', 'RED'] as const).map((side) => (
            <div key={side}>
              <strong>{replay.players[side].team}</strong>
              <span>
                {side === 'BLUE' ? 'Xanh' : 'Đỏ'} · {(clocks[side] / 1000).toFixed(2)}s
              </span>
            </div>
          ))}
        </div>
        <svg className="board" viewBox="-22 -18 410 405" role="img" aria-label={`Bàn cờ sau nước ${step}`}>
          {board.map((piece, index) => {
            const x = (index % 9) * 40,
              y = (8 - Math.floor(index / 9)) * 40;
            const highlight =
              move && [squareIndex(move.move.slice(0, 2)), squareIndex(move.move.slice(2))].includes(index);
            const color = piece === piece?.toUpperCase() ? '#147dba' : '#d55449';
            return (
              <g key={index}>
                <rect
                  className={`replay-tile ${index % 2 ? 'light' : 'dark'} ${[0, 80].includes(index) ? 'goal' : ''} ${highlight ? 'last' : ''}`}
                  x={x}
                  y={y}
                  width="40"
                  height="40"
                  fill={
                    highlight
                      ? '#f4cf6d'
                      : [0, 80].includes(index)
                        ? '#b1cec0'
                        : index % 2
                          ? '#eee9dc'
                          : '#d8dfd3'
                  }
                  stroke="#b5c0b5"
                  strokeWidth=".5"
                />
                {piece && (
                  <g
                    className={`replay-piece ${piece === piece.toUpperCase() ? 'BLUE' : 'RED'}`}
                    fill={color}
                    stroke="#fff"
                    strokeWidth="2"
                  >
                    {piece.toUpperCase() === 'B' ? (
                      <circle cx={x + 20} cy={y + 20} r="13" />
                    ) : piece.toUpperCase() === 'P' ? (
                      <rect x={x + 7} y={y + 7} width="26" height="26" rx="3" />
                    ) : (
                      <path d={`M${x + 20} ${y + 5} L${x + 35} ${y + 33} L${x + 5} ${y + 33} Z`} />
                    )}
                    <title>{`${String.fromCharCode(97 + (index % 9))}${Math.floor(index / 9) + 1}: ${piece}`}</title>
                  </g>
                )}
              </g>
            );
          })}
          {Array.from({ length: 9 }, (_, i) => (
            <g key={i} fontSize="12" fill="currentColor">
              <text x={i * 40 + 16} y="378">
                {String.fromCharCode(97 + i)}
              </text>
              <text x="-16" y={i * 40 + 24}>
                {9 - i}
              </text>
            </g>
          ))}
        </svg>
        <div className="controls">
          <button onClick={() => jump(0)} aria-label="Về đầu">
            |◀
          </button>
          <button onClick={() => jump(step - 1)} aria-label="Lùi">
            ◀
          </button>
          <button
            onClick={() => {
              if (step === replay.moves.length) setPly(0);
              setPlaying(!playing);
            }}
            disabled={!replay.moves.length}
          >
            {playing ? 'Dừng' : 'Phát'}
          </button>
          <button onClick={() => jump(step + 1)} aria-label="Tiến">
            ▶
          </button>
          <button onClick={() => jump(replay.moves.length)} aria-label="Về cuối">
            ▶|
          </button>
          <select aria-label="Tốc độ phát" value={speed} onChange={(e) => setSpeed(Number(e.target.value))}>
            <option value={1000}>0.5×</option>
            <option value={500}>1×</option>
            <option value={250}>2×</option>
          </select>
        </div>
        <input
          aria-label="Nước đi"
          type="range"
          min="0"
          max={replay.moves.length}
          value={step}
          onChange={(e) => jump(Number(e.target.value))}
        />
        <p>
          Nước {step}/{replay.moves.length} ·{' '}
          {move ? `${move.think_ms}ms · Ăn: ${move.capture ?? 'không'}` : 'Vị trí ban đầu'}
        </p>
        <p>
          {replay.result.winner === 'BLUE' ? 'Xanh' : 'Đỏ'} thắng · {reasons[replay.result.reason]}
        </p>
        <small>
          {'BPKbpk'
            .split('')
            .map((p) => `${p}: ${board.filter((v) => v === p).length}`)
            .join(' · ')}
        </small>
        {props.onDownload && (
          <p>
            <button onClick={props.onDownload}>Tải replay JSON</button>
          </p>
        )}
      </div>
      <div>
        <h3>Các nước đi</h3>
        <div className="move-list">
          {replay.moves.map((m) => (
            <button className={step === m.ply ? 'selected' : ''} key={m.ply} onClick={() => jump(m.ply)}>
              {m.ply}. {m.move}
            </button>
          ))}
        </div>
        <h3>Debug tại nước {step}</h3>
        <pre>{move?.debug.join('\n') || 'Không có debug.'}</pre>
        {props.mode === 'admin' && props.stderr && (
          <details>
            <summary>stderr hai bên (quản trị)</summary>
            <h4>Xanh</h4>
            <pre>{props.stderr.BLUE}</pre>
            <h4>Đỏ</h4>
            <pre>{props.stderr.RED}</pre>
          </details>
        )}
      </div>
    </section>
  );
}
