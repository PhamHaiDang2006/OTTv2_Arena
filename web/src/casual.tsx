import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { parseFen } from '@ottv2/replay-viewer';
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

const reasons: Record<string, string> = {
  GOAL: 'Chiếm ô mục tiêu',
  WIPEOUT: 'Ăn hết quân',
  STALEMATE: 'Hết nước đi',
  MOVE_LIMIT: 'Phân định sau 300 nước',
  RESIGNED: 'Đầu hàng',
};
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
  return (
    <>
      <Heading
        eyebrow="OTT v2 / CASUAL"
        title="Casual · Chơi với máy"
        description="Bàn cờ và bot mẫu chạy trên trình duyệt. Không ảnh hưởng kết quả Arena."
      />
      <form
        className="card"
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
        <button className="primary">Bắt đầu chơi</button>
        <ErrorBox error={error} />
      </form>
      <h2>Ván của bạn</h2>
      <p className="muted">
        Lưu {MAX_SAVED_GAMES} ván gần nhất trên trình duyệt này; máy hoặc trình duyệt khác không thấy các ván
        này.
      </p>
      <div className="casual-history">
        {games.length ? (
          games.map((game) => (
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
    </>
  );
}

export function CasualBoard({
  game,
  busy,
  onMove,
}: {
  game: CasualGame;
  busy: boolean;
  onMove: (move: string) => void;
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
  const glyphs: Record<string, string> = { B: '●', P: '■', K: '▲' };
  return (
    <div className="casual-board" role="group" aria-label="Bàn cờ OTTv2 9 nhân 9">
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
            className={`casual-square ${((index % 9) + Math.floor(index / 9)) % 2 ? 'dark' : ''} ${side ?? ''} ${goal ? 'goal' : ''} ${selected === square ? 'selected' : ''} ${target ? 'target' : ''} ${last?.includes(square) ? 'last-move' : ''}`}
            onClick={() => {
              if (target && selected) {
                setSelected(null);
                onMove(selected + square);
              } else setSelected(selected === square ? null : square);
            }}
          >
            <small>{square}</small>
            <span aria-hidden="true">
              {piece ? glyphs[piece.toUpperCase()] : goal ? '☆' : target ? '·' : ''}
            </span>
          </button>
        );
      })}
    </div>
  );
}

export function CasualPlay({ user }: { user: User }) {
  const { id } = useParams<{ id: string }>();
  const [games, reload] = useCasualGames(user.id);
  const game = games.find((g) => g.id === id);
  const [error, setError] = useState<unknown>(),
    [confirm, setConfirm] = useState(false),
    [busy, setBusy] = useState(false);
  useEffect(() => {
    setError(undefined);
    setConfirm(false);
  }, [id]);
  function act(current: CasualGame, move?: string) {
    setError(undefined);
    setBusy(true);
    updateGame(user.id, current, (g) => (move ? playMove(g, move) : resign(g)))
      .catch(setError)
      .finally(() => {
        reload();
        setBusy(false);
        setConfirm(false);
      });
  }
  return (
    <>
      <Heading
        eyebrow="OTT v2 / CASUAL"
        title="Casual · Bàn cờ của bạn"
        description="Chọn quân của bạn, rồi chọn ô được đánh dấu."
      >
        <Link className="button" to="/casual">
          Về Casual / Ván mới
        </Link>
      </Heading>
      {!game ? (
        <section className="card">
          <p>Không tìm thấy ván này trên trình duyệt. Ván Casual chỉ lưu trên trình duyệt đã tạo ván.</p>
          <ErrorBox error={error} />
        </section>
      ) : (
        <div className="casual-layout">
          <section className="card">
            <p className="casual-status" role="status">
              {game.status === 'finished'
                ? `${game.winner === game.human_side ? 'Bạn thắng!' : 'Máy thắng'} · ${reasons[game.reason!]}`
                : 'Đến lượt của bạn'}
            </p>
            <CasualBoard game={game} busy={busy} onMove={(move) => act(game, move)} />
            <p>
              Bạn: <strong>{game.human_side === 'BLUE' ? 'Xanh' : 'Đỏ'}</strong> · Máy: {botNames[game.bot]} ·{' '}
              {game.ply}/300 nước
            </p>
            <ErrorBox error={error} />
            {game.status === 'playing' &&
              (!confirm ? (
                <button onClick={() => setConfirm(true)}>Đầu hàng</button>
              ) : (
                <div role="group" aria-label="Xác nhận đầu hàng">
                  <p>Đầu hàng sẽ kết thúc ván này với phần thắng cho máy.</p>
                  <button disabled={busy} onClick={() => act(game)}>
                    Xác nhận đầu hàng
                  </button>{' '}
                  <button onClick={() => setConfirm(false)}>Tiếp tục chơi</button>
                </div>
              ))}
          </section>
          <aside className="card">
            <h2>Cách chơi</h2>
            <p>● Búa ăn ▲ Kéo · ▲ Kéo ăn ■ Bao · ■ Bao ăn ● Búa.</p>
            <p>
              Mỗi lượt đi một ô theo tám hướng. Không đi vào ô có quân mình hoặc quân đối phương mà bạn không
              ăn được.
            </p>
            <p>Xanh cần chiếm i9; Đỏ cần chiếm a1. Không được đi vào ô mục tiêu của đối thủ.</p>
            <p>Không tính giờ; có thể rời trang và tiếp tục từ danh sách ván Casual trên trình duyệt này.</p>
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
    </>
  );
}
