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
import { PieceIcon, Crest, MiniBoard, GameResult, historyFrame, resultReasons } from './casual-presentation';
import { useGameSound, useReducedMotion } from './preferences';

export function Modes() {
  return (
    <>
      <Heading
        eyebrow="OTT v2 / CHỌN CHẾ ĐỘ"
        title="Bạn muốn chơi theo cách nào?"
        description="Cùng bàn cờ OTTv2, mỗi chế độ chạy ở một nơi khác nhau."
      />
      <div className="mode-cards">
        <section className="card mode-card casual-mode">
          <span className="eyebrow">CHẠY TRÊN TRÌNH DUYỆT</span>
          <h2>Casual</h2>
          <p>Chọn quân, chọn ô và thử chiến thuật với bot mẫu. Bàn cờ và bot chạy ngay trong trình duyệt.</p>
          <p>Đấu với bot mẫu · Không tính giờ · Lưu ván trên trình duyệt này</p>
          <Link className="button primary" to="/casual">
            Chơi với máy →
          </Link>
        </section>
        <section className="card mode-card practice-mode">
          <span className="eyebrow">CHẠY TRÊN MÁY CỦA BẠN</span>
          <h2>Tự luyện</h2>
          <p>Cho bot của bạn đấu với bot mẫu hoặc một bot khác có sẵn trên máy, rồi xem replay tại đây.</p>
          <p>Bộ khởi động · Không cần nộp bài · Không tốn lượt đánh tập</p>
          <Link className="button" to="/practice">
            Hướng dẫn tự luyện →
          </Link>
        </section>
        <section className="card mode-card">
          <span className="eyebrow">ĐẤU TRƯỜNG TRÊN MÁY CHỦ</span>
          <h2>Arena</h2>
          <p>Nộp bot, đánh tập với đội khác và thi đấu giải. Giải chính thức có máy chạy riêng.</p>
          <p>Đội thi đấu · Nộp code · Đánh tập · Giải đấu</p>
          <Link className="button" to="/arena">
            Vào Arena →
          </Link>
        </section>
      </div>
    </>
  );
}

const botNames = { random: 'Bot ngẫu nhiên', greedy: 'Bot ưu tiên ăn quân' };
/** Games of this account in this browser; follows changes made in other tabs. */
function useCasualGames(userId: string) {
  const [games, setGames] = useState(() => loadGames(userId));
  const reload = useCallback(() => setGames(loadGames(userId)), [userId]);
  useEffect(() => {
    reload();
    const onStorage = (event: StorageEvent) => {
      if (isCasualStorageKey(event.key, userId)) reload();
    };
    window.addEventListener('storage', onStorage);
    return () => window.removeEventListener('storage', onStorage);
  }, [userId, reload]);
  return [games, reload] as const;
}
export function CasualLobby({ user }: { user: User }) {
  const navigate = useNavigate();
  const [games] = useCasualGames(user.id);
  const [error, setError] = useState<unknown>();
  const [bot, setBot] = useState<CasualBot>('random');
  return (
    <div className="casual-lobby">
      <div className="lobby-hero">
        <Heading
          eyebrow="OTT v2 / CASUAL"
          title="Casual · Chơi với máy"
          description="Một bàn cờ. Vô vàn cách chiến thắng. Chọn đối thủ và tìm nước đi của riêng bạn."
        />
        <div className="hero-pieces" aria-hidden="true">
          {['B', 'P', 'K'].map((p, i) => (
            <span key={p} className={`hero-piece hero-piece-${i}`}>
              <PieceIcon piece={p} />
            </span>
          ))}
        </div>
        <div className="lobby-pills">
          <span>9 × 9 ô cờ</span>
          <span>Không áp lực thời gian</span>
          <span>Chơi ngay trên máy bạn</span>
        </div>
      </div>
      <form
        className="card lobby-setup"
        onSubmit={(e) => {
          e.preventDefault();
          const fields = new FormData(e.currentTarget);
          const game = newGame(fields.get('side') as Side, fields.get('bot') as CasualBot);
          setError(undefined);
          withGamesLock(user.id, () => saveGame(user.id, game))
            .catch(setError)
            .finally(() => navigate(`/casual/${game.id}`));
        }}
      >
        <div className="section-title">
          <span className="eyebrow">01 / CHỌN THỬ THÁCH</span>
          <h2>Bắt đầu một ván</h2>
        </div>
        <div className="bot-choices" role="group" aria-label="Phong cách đối thủ">
          {(['random', 'greedy'] as const).map((choice) => (
            <button
              key={choice}
              type="button"
              className={`bot-choice ${choice === bot ? 'chosen' : ''}`}
              aria-pressed={choice === bot}
              onClick={() => setBot(choice)}
            >
              <span className={`bot-portrait ${choice}`}>
                <Crest kind="bot" />
              </span>
              <span className="bot-copy">
                <span className="eyebrow">{choice === 'random' ? 'LÀM QUEN' : 'THỬ CHIẾN THUẬT'}</span>
                <strong>{botNames[choice]}</strong>
                <span>
                  {choice === 'random'
                    ? 'Những nước đi bất ngờ. Thoải mái khám phá luật chơi.'
                    : 'Luôn tìm cơ hội ăn quân. Hãy bảo vệ đội hình của bạn.'}
                </span>
              </span>
              <span className="choice-dot" aria-hidden="true">
                {choice === bot ? '✓' : ''}
              </span>
            </button>
          ))}
        </div>
        <div className="setup-controls">
          <Field label="Đối thủ">
            <select name="bot" value={bot} onChange={(e) => setBot(e.target.value as CasualBot)}>
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
          <button className="primary">Bắt đầu chơi</button>
        </div>
        <p className="setup-footnote">Xanh đi trước · Tối đa 300 nước · Luật phát triển dev-v1</p>
        <ErrorBox error={error} />
      </form>
      <div className="section-title">
        <span className="eyebrow">02 / HÀNH TRÌNH CỦA BẠN</span>
        <h2>Ván của bạn</h2>
      </div>
      <p className="muted">
        Lưu {MAX_SAVED_GAMES} ván gần nhất trên trình duyệt này; máy hoặc trình duyệt khác không thấy các ván
        này.
      </p>
      <div className="casual-history">
        {games.length ? (
          games.map((game) => (
            <Link className="card" key={game.id} to={`/casual/${game.id}`}>
              <MiniBoard fen={game.fen} />
              <div className="saved-game-info">
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
              </div>
              <span className="saved-arrow" aria-hidden="true">
                ↗
              </span>
            </Link>
          ))
        ) : (
          <div className="lobby-empty">
            <Crest />
            <div>
              <strong>Nước đi đầu tiên đang chờ bạn.</strong>
              <p>Chưa có ván nào. Chọn đối thủ và bắt đầu nhé.</p>
            </div>
          </div>
        )}
      </div>
    </div>
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
                {goal ? <Crest /> : target ? '·' : ''}
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

export function CasualPlay({ user }: { user: User }) {
  const { id } = useParams<{ id: string }>();
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
  useEffect(() => {
    epoch.current++;
    pending.current = false;
    setBusy(false);
    setPresentation(undefined);
    setPhase('');
    setError(undefined);
    setConfirm(false);
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
          <Crest kind={bot ? 'bot' : 'player'} />
        </span>
        <div>
          <strong>{bot ? botNames[game!.bot] : 'Bạn'}</strong>
          <small>
            {side === 'BLUE' ? 'Quân xanh' : 'Quân đỏ'} · {count} quân
          </small>
        </div>
        <div className="piece-inventory" aria-label="Quân còn lại">
          {['B', 'P', 'K'].map((p) => (
            <span key={p}>
              <span className="sr-only">{p === 'B' ? 'Búa' : p === 'P' ? 'Bao' : 'Kéo'}: </span>
              <PieceIcon piece={p} />
              <b>
                {
                  parseFen(display!.fen).filter((cell) => cell === (side === 'BLUE' ? p : p.toLowerCase()))
                    .length
                }
              </b>
            </span>
          ))}
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
              <p>
                Mỗi lượt đi một ô theo tám hướng. Không đi vào ô có quân mình hoặc quân đối phương mà bạn
                không ăn được.
              </p>
              <p>Xanh cần chiếm i9; Đỏ cần chiếm a1. Không được đi vào ô mục tiêu của đối thủ.</p>
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
    </>
  );
}
