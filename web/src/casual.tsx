<<<<<<< Updated upstream
import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { parseFen } from '@ottv2/replay-viewer';
import type { CasualGame, Side } from '../../contracts/generated/types';
import { api } from './api';
import { ErrorBox, Field, Heading, Load, Pager, useApi } from './ui';
=======
import { useCallback, useEffect, useRef, useState, type CSSProperties } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { applyMove, toFen, parseFen } from '@ottv2/replay-viewer';
import type { Side, User } from '../../contracts/generated/types';
import {
  MAX_SAVED_GAMES,
  isCasualStorageKey,
  loadGames,
  newGame,
  playMove,
  resign,
  saveGame,
  updateGame,
  withGamesLock,
  type CasualBot,
  type CasualGame,
} from './casual-engine';
import { ErrorBox, Field, Heading } from './ui';
import { PieceIcon, GameResult, historyFrame, resultReasons } from './casual-presentation';
import { useGameSound, useReducedMotion } from './preferences';
>>>>>>> Stashed changes

export function Modes() {
  return (
    <>
      <Heading
        eyebrow="OTT v2 / CHỌN CHẾ ĐỘ"
        title="Bạn muốn chơi theo cách nào?"
        description="Cùng bàn cờ OTTv2, hai cách trải nghiệm."
      />
      <div className="mode-cards">
        <section className="card mode-card casual-mode">
          <span className="eyebrow">CHƠI TRỰC TIẾP</span>
          <h2>Casual</h2>
          <p>Chọn quân, chọn ô và thử chiến thuật với máy. Không cần viết code hay chờ duyệt đội.</p>
          <p>Đấu với bot mẫu · Không tính giờ · Lưu ván đang chơi</p>
          <Link className="button primary" to="/casual">
            Chơi với máy →
          </Link>
        </section>
        <section className="card mode-card">
          <span className="eyebrow">ĐẤU TRƯỜNG LẬP TRÌNH</span>
          <h2>Arena</h2>
          <p>Đưa thuật toán của bạn vào thi đấu. Nộp bot, đánh tập, tham gia giải và xem replay.</p>
          <p>Đội thi đấu · Nộp code · Giải đấu</p>
          <Link className="button" to="/arena">
            Vào Arena →
          </Link>
        </section>
      </div>
    </>
  );
}

const botNames = { random: 'Bot ngẫu nhiên', greedy: 'Bot ưu tiên ăn quân' };
export function CasualLobby() {
  const navigate = useNavigate();
  const [page, setPage] = useState(1),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>();
  const games = useApi('listCasualGames', { query: { page, page_size: 20 } });
  return (
    <>
      <Heading
        eyebrow="OTT v2 / CASUAL"
        title="Casual · Chơi với máy"
        description="Chơi bằng thao tác trên bàn cờ. Không ảnh hưởng kết quả Arena."
      />
      <form
        className="card"
        onSubmit={async (e) => {
          e.preventDefault();
          if (busy) return;
          const fields = new FormData(e.currentTarget);
          setBusy(true);
          setError(undefined);
          try {
            const game = await api('createCasualGame', {
              human_side: fields.get('side') as Side,
              bot: fields.get('bot') as 'random' | 'greedy',
            });
            navigate(`/casual/${game.id}`);
          } catch (err) {
            setError(err);
            void games.refetch();
          } finally {
            setBusy(false);
          }
        }}
      >
        <h2>Bắt đầu một ván</h2>
        <Field label="Đối thủ">
          <select name="bot">
            <option value="random">Bot ngẫu nhiên — làm quen</option>
            <option value="greedy">Bot ưu tiên ăn quân — thử chiến thuật</option>
          </select>
        </Field>
        <Field label="Màu quân của bạn">
          <select name="side">
            <option value="BLUE">Xanh — đi trước</option>
            <option value="RED">Đỏ — đi sau</option>
          </select>
        </Field>
        <p className="muted">Không tính giờ. Xanh đi trước. Mỗi ván tối đa 300 nước theo luật dev-v1.</p>
        <button className="primary" disabled={busy}>
          {busy ? 'Đang tạo ván…' : 'Bắt đầu chơi'}
        </button>
        <ErrorBox error={error} />
      </form>
      <h2>Ván của bạn</h2>
      <Load query={games}>
        {(data) => (
          <>
            <div className="casual-history">
              {data.items.length ? (
                data.items.map((game) => (
                  <Link className="card" key={game.id} to={`/casual/${game.id}`}>
                    <strong>{botNames[game.bot]}</strong>
                    <span>
                      {game.status === 'playing'
                        ? 'Tiếp tục chơi'
                        : game.winner === game.human_side
                          ? 'Bạn thắng'
                          : 'Máy thắng'}{' '}
                      · {game.ply} nước
                    </span>
                    <small>{new Date(game.created_at).toLocaleString('vi-VN')}</small>
                  </Link>
                ))
              ) : (
                <p>Chưa có ván nào. Chọn đối thủ và bắt đầu nhé.</p>
              )}
            </div>
            <Pager page={page} total={data.total} setPage={setPage} />
          </>
        )}
      </Load>
    </>
  );
}

export function CasualBoard({
  game,
  busy,
  onMove,
  animate = false,
}: {
  game: CasualGame;
  busy: boolean;
  onMove: (move: string) => void;
  animate?: boolean;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  useEffect(() => setSelected(null), [game.id, game.ply, game.status]);
  const cells = parseFen(game.fen);
  const indices = Array.from({ length: 81 }, (_, i) => (8 - Math.floor(i / 9)) * 9 + (i % 9));
  if (game.human_side === 'RED') indices.reverse();
  const sources = new Set(game.legal_moves.map((move) => move.slice(0, 2)));
  const targets = new Set(
    game.legal_moves.filter((move) => move.startsWith(selected ?? '!')).map((move) => move.slice(2)),
  );
  const last = game.moves.at(-1)?.move;
  const names: Record<string, string> = { B: 'Búa', P: 'Bao', K: 'Kéo' };
  const record = game.moves.at(-1);
  const direction = game.human_side === 'RED' ? -1 : 1;
  const movement = last
    ? ({
        '--move-x': `${(last.charCodeAt(0) - last.charCodeAt(2)) * 100 * direction}%`,
        '--move-y': `${(Number(last[3]) - Number(last[1])) * 100 * direction}%`,
      } as CSSProperties)
    : undefined;
  return (
    <div
      className="casual-board"
      role="group"
      aria-label="Bàn cờ OTTv2 9 nhân 9"
      onKeyDown={(e) => {
        if (e.key === 'Escape') setSelected(null);
      }}
    >
      {indices.map((index) => {
        const square = String.fromCharCode(97 + (index % 9)) + (Math.floor(index / 9) + 1);
        const piece = cells[index],
          side = piece && (piece === piece.toUpperCase() ? 'BLUE' : 'RED');
        const target = targets.has(square),
          goal = index === 0 || index === 80;
        return (
          <button
            key={square}
            type="button"
            aria-label={`${square}: ${piece ? `${names[piece.toUpperCase()]} ${side === 'BLUE' ? 'xanh' : 'đỏ'}` : 'trống'}${target ? ', có thể đi tới' : ''}`}
            aria-pressed={selected === square}
            disabled={busy || game.status !== 'playing' || (!sources.has(square) && !target)}
            className={`casual-square ${((index % 9) + Math.floor(index / 9)) % 2 ? 'dark' : ''} ${side ?? ''} ${goal ? 'goal' : ''} ${selected === square ? 'selected' : ''} ${target ? 'target' : ''} ${last?.slice(0, 2) === square ? 'last-from' : ''} ${last?.slice(2) === square ? 'last-to' : ''}`}
            onClick={() => {
              if (target && selected) {
                setSelected(null);
                onMove(selected + square);
              } else setSelected(selected === square ? null : square);
            }}
          >
            <small>{square}</small>
            {piece ? (
              <span
                key={`${game.id}-${game.ply}-${square}`}
                className={`piece-slot ${animate && last?.slice(2) === square ? 'piece-moving' : ''}`}
                style={movement}
              >
                <span className="piece-token">
                  <PieceIcon piece={piece} />
                </span>
              </span>
            ) : (
              <span className="square-mark" aria-hidden="true">
                {goal ? '☆' : target ? '·' : ''}
              </span>
            )}
            {animate && last?.slice(2) === square && record?.capture && (
              <span
                key={`capture-${game.ply}`}
                className={`captured-piece ${record.capture === record.capture.toUpperCase() ? 'BLUE' : 'RED'}`}
              >
                <PieceIcon piece={record.capture} />
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}

export function CasualPlay() {
  const { id } = useParams<{ id: string }>();
<<<<<<< Updated upstream
  const query = useApi('getCasualGame', { path: { id: id! } }, !!id, 5000);
  const cache = useQueryClient();
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(),
    [confirm, setConfirm] = useState(false);
=======
  const navigate = useNavigate();
  const [games, reload] = useCasualGames(user.id);
  const saved = games.find((g) => g.id === id);
  const [error, setError] = useState<unknown>(),
    [confirm, setConfirm] = useState(false),
    [busy, setBusy] = useState(false);
  const [presentation, setPresentation] = useState<CasualGame>(),
    [phase, setPhase] = useState('');
  const [review, setReview] = useState(false),
    [reviewPly, setReviewPly] = useState(0);
  const epoch = useRef(0),
    pending = useRef(false);
  const reduced = useReducedMotion(),
    sound = useGameSound();
>>>>>>> Stashed changes
  useEffect(() => {
    epoch.current++;
    pending.current = false;
    setBusy(false);
    setPresentation(undefined);
    setPhase('');
    setError(undefined);
    setConfirm(false);
<<<<<<< Updated upstream
  }, [id]);
  async function act(game: CasualGame, move?: string) {
    if (busy) return;
    setBusy(true);
    setError(undefined);
    try {
      await cache.cancelQueries({ queryKey: ['getCasualGame', { id: game.id }] });
      const state = move
        ? await api('moveCasualGame', { move, expected_ply: game.ply }, { path: { id: game.id } })
        : await api('resignCasualGame', { expected_ply: game.ply }, { path: { id: game.id } });
      cache.setQueryData(['getCasualGame', { id: game.id }, undefined], state);
      void cache.invalidateQueries({ queryKey: ['listCasualGames'] });
    } catch (err) {
      setError(err);
      await query.refetch();
    } finally {
      setBusy(false);
      setConfirm(false);
=======
    setReview(false);
    reload();
    return () => {
      epoch.current++;
    };
  }, [id, user.id, reload]);
  const game = presentation?.id === id ? presentation : saved;
  async function act(current: CasualGame, move?: string) {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError(undefined);
    sound.unlock();
    const token = epoch.current;
    try {
      // Persist the complete turn under the existing lock before animating it.
      const next = await updateGame(user.id, current, (g) => (move ? playMove(g, move) : resign(g)));
      if (token !== epoch.current) return;
      if (move && !reduced) {
        const added = next.moves.slice(current.ply);
        let board = parseFen(current.fen);
        for (let i = 0; i < added.length; i++) {
          const record = added[i];
          board = applyMove(board, record.move);
          const last = i === added.length - 1;
          setPresentation(
            last
              ? next
              : {
                  ...current,
                  fen: toFen(board),
                  ply: current.ply + i + 1,
                  moves: next.moves.slice(0, current.ply + i + 1),
                  legal_moves: [],
                },
          );
          setPhase(record.side === current.human_side && !last ? 'Máy đang đi…' : 'Đang đi quân…');
          sound.play(!!record.capture);
          await new Promise((resolve) => setTimeout(resolve, last ? 280 : 560));
          if (token !== epoch.current) return;
        }
      } else if (move) sound.play(next.moves.slice(current.ply).some((m) => !!m.capture));
    } catch (err) {
      if (token === epoch.current) setError(err);
    } finally {
      if (token === epoch.current) {
        reload();
        setPresentation(undefined);
        setBusy(false);
        pending.current = false;
        setConfirm(false);
        setPhase('');
      }
>>>>>>> Stashed changes
    }
  }
  async function again() {
    if (!saved || pending.current) return;
    pending.current = true;
    setBusy(true);
    setError(undefined);
    const token = epoch.current,
      next = newGame(saved.human_side, saved.bot);
    try {
      await withGamesLock(user.id, () => saveGame(user.id, next));
      if (token === epoch.current) navigate(`/casual/${next.id}`);
    } catch (err) {
      if (token === epoch.current) setError(err);
    } finally {
      if (token === epoch.current) {
        pending.current = false;
        setBusy(false);
      }
    }
  }
  const display = game && review ? historyFrame(game, reviewPly) : game;
  const active =
    busy && phase.startsWith('Máy') ? (game?.human_side === 'BLUE' ? 'RED' : 'BLUE') : game?.human_side;
  const player = (bot: boolean) => {
    const side = bot ? (game!.human_side === 'BLUE' ? 'RED' : 'BLUE') : game!.human_side;
    const count = parseFen(display!.fen).filter(
      (piece) => piece && (piece === piece.toUpperCase()) === (side === 'BLUE'),
    ).length;
    return (
      <div
        className={`player-strip ${side} ${game!.status === 'playing' && !review && active === side ? 'is-active' : ''}`}
      >
        <span className="player-avatar" aria-hidden="true">
          {bot ? '⚙' : '♙'}
        </span>
        <div>
          <strong>{bot ? botNames[game!.bot] : 'Bạn'}</strong>
          <small>
            {side === 'BLUE' ? 'Quân xanh' : 'Quân đỏ'} · {count} quân
          </small>
        </div>
        <span className="player-indicator">
          {game!.status === 'playing' && !review && active === side
            ? 'Đang chơi'
            : bot
              ? 'Đối thủ'
              : 'Người chơi'}
        </span>
      </div>
    );
  };
  return (
    <>
      <Heading eyebrow="OTT v2 / CASUAL" title="Bàn cờ của bạn" description="Một nước đi, một ý tưởng mới.">
        <div className="game-tools">
          <button type="button" aria-pressed={sound.enabled} onClick={sound.toggle}>
            Âm thanh: {sound.enabled ? 'Bật' : 'Tắt'}
          </button>
          <Link className="button" to="/casual">
            Về sảnh
          </Link>
        </div>
      </Heading>
<<<<<<< Updated upstream
      <Load query={query}>
        {(game) => (
          <div className="casual-layout">
            <section className="card">
              <p className="casual-status" role="status">
                {game.status === 'finished'
                  ? `${game.winner === game.human_side ? 'Bạn thắng!' : 'Máy thắng'} · ${reasons[game.reason!]}`
                  : busy
                    ? 'Đang xử lý nước đi…'
                    : 'Đến lượt của bạn'}
              </p>
              <CasualBoard game={game} busy={busy} onMove={(move) => void act(game, move)} />
              <p>
                Bạn: <strong>{game.human_side === 'BLUE' ? 'Xanh' : 'Đỏ'}</strong> · Máy: {botNames[game.bot]}{' '}
                · {game.ply}/300 nước
              </p>
              <ErrorBox error={error} />
              {game.status === 'playing' &&
                (!confirm ? (
                  <button disabled={busy} onClick={() => setConfirm(true)}>
                    Đầu hàng
                  </button>
                ) : (
                  <div role="group" aria-label="Xác nhận đầu hàng">
                    <p>Đầu hàng sẽ kết thúc ván này với phần thắng cho máy.</p>
                    <button disabled={busy} onClick={() => void act(game)}>
                      Xác nhận đầu hàng
                    </button>{' '}
                    <button disabled={busy} onClick={() => setConfirm(false)}>
                      Tiếp tục chơi
                    </button>
                  </div>
                ))}
            </section>
            <aside className="card">
              <h2>Cách chơi</h2>
              <p>● Búa ăn ▲ Kéo · ▲ Kéo ăn ■ Bao · ■ Bao ăn ● Búa.</p>
=======
      {!game || !display ? (
        <section className="card">
          <p>Không tìm thấy ván này trên trình duyệt. Ván Casual chỉ lưu trên trình duyệt đã tạo ván.</p>
          <ErrorBox error={error} />
        </section>
      ) : (
        <div className="casual-layout">
          <section className="casual-stage">
            {player(true)}
            <div className="board-housing">
              <div className="board-status">
                <p role="status">
                  {review
                    ? `Xem lại · Nước ${reviewPly}/${game.ply}`
                    : busy
                      ? phase || 'Đang xử lý…'
                      : game.status === 'finished'
                        ? `${game.winner === game.human_side ? 'Bạn thắng!' : 'Máy thắng'} · ${resultReasons[game.reason!]}`
                        : 'Đến lượt của bạn'}
                </p>
                <span>{display.ply} / 300</span>
              </div>
              <CasualBoard
                game={display}
                busy={busy || review}
                animate={!!presentation && !reduced}
                onMove={(move) => void act(game, move)}
              />
              <p className="board-hint">
                {review
                  ? 'Dùng thanh bên dưới để xem từng nước.'
                  : 'Chọn quân → chọn ô sáng để đi · Esc để bỏ chọn'}
              </p>
            </div>
            {player(false)}
            <ErrorBox error={error} />
            {review && (
              <div className="review-controls">
                <button disabled={reviewPly === 0} onClick={() => setReviewPly((p) => p - 1)}>
                  ← Trước
                </button>
                <input
                  aria-label="Nước xem lại"
                  type="range"
                  min={0}
                  max={game.ply}
                  value={reviewPly}
                  onChange={(e) => setReviewPly(Number(e.target.value))}
                />
                <button disabled={reviewPly === game.ply} onClick={() => setReviewPly((p) => p + 1)}>
                  Sau →
                </button>
                <button onClick={() => setReview(false)}>Xem kết quả</button>
              </div>
            )}
            {game.status === 'playing' &&
              (!confirm ? (
                <button className="resign-button" disabled={busy} onClick={() => setConfirm(true)}>
                  Đầu hàng
                </button>
              ) : (
                <div className="card" role="group" aria-label="Xác nhận đầu hàng">
                  <p>Đầu hàng sẽ kết thúc ván này với phần thắng cho máy.</p>
                  <button disabled={busy} onClick={() => void act(game)}>
                    Xác nhận đầu hàng
                  </button>{' '}
                  <button disabled={busy} onClick={() => setConfirm(false)}>
                    Tiếp tục chơi
                  </button>
                </div>
              ))}
          </section>
          <aside className="casual-aside">
            <details className="card" open>
              <summary>
                Lịch sử nước đi <span className="tag">{game.ply}</span>
              </summary>
              <ol className="casual-moves">
                {game.moves.map((record, i) => (
                  <li key={i} className={review && reviewPly === i + 1 ? 'review-current' : ''}>
                    <span className={`move-side ${record.side}`}>
                      {record.side === 'BLUE' ? 'Xanh' : 'Đỏ'}
                    </span>
                    <strong>
                      {record.move.slice(0, 2)} → {record.move.slice(2)}
                    </strong>
                    {record.capture && <span className="capture-label">Ăn quân</span>}
                  </li>
                ))}
              </ol>
              {!game.moves.length && <p className="muted">Hãy đi nước đầu tiên.</p>}
            </details>
            <details className="card">
              <summary>Cách chơi</summary>
              <div className="piece-legend">
                {['B', 'P', 'K'].map((piece) => (
                  <span key={piece}>
                    <PieceIcon piece={piece} />
                    {({ B: 'Búa', P: 'Bao', K: 'Kéo' } as Record<string, string>)[piece]}
                  </span>
                ))}
              </div>
              <p>Búa ăn Kéo · Kéo ăn Bao · Bao ăn Búa.</p>
>>>>>>> Stashed changes
              <p>
                Mỗi lượt đi một ô theo tám hướng. Không đi vào ô có quân mình hoặc quân đối phương mà bạn
                không ăn được.
              </p>
              <p>Xanh cần chiếm i9; Đỏ cần chiếm a1. Không được đi vào ô mục tiêu của đối thủ.</p>
<<<<<<< Updated upstream
              <p>Không tính giờ; có thể rời trang và tiếp tục từ danh sách ván Casual.</p>
              <h2>Lịch sử nước đi</h2>
              <ol className="casual-moves">
                {game.moves.map((move, i) => (
                  <li key={i}>
                    <span>{move.side === 'BLUE' ? 'Xanh' : 'Đỏ'}</span>{' '}
                    <strong>
                      {move.move.slice(0, 2)} → {move.move.slice(2)}
                    </strong>
                    {move.capture ? ' · ăn quân' : ''}
                  </li>
                ))}
              </ol>
              {!game.moves.length && <p>Hãy đi nước đầu tiên.</p>}
            </aside>
          </div>
        )}
      </Load>
=======
              <p>Không tính giờ. Ván được lưu trên trình duyệt này.</p>
            </details>
            <div className="casual-note">
              <span className="eyebrow">CHƠI ĐỂ KHÁM PHÁ</span>
              <p>
                Thử một hướng đi mới.
                <br />
                Mỗi ván đều có điều để học.
              </p>
            </div>
          </aside>
        </div>
      )}
      {saved?.status === 'finished' && !presentation && !review && (
        <GameResult
          game={saved}
          busy={busy}
          error={error instanceof Error ? error.message : undefined}
          onAgain={() => void again()}
          onReview={() => {
            setReviewPly(saved.ply);
            setReview(true);
          }}
          onLobby={() => navigate('/casual')}
        />
      )}
>>>>>>> Stashed changes
    </>
  );
}
