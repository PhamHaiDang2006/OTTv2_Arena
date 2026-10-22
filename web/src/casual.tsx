import { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import { parseFen } from '@ottv2/replay-viewer';
import type { CasualGame, Side } from '../../contracts/generated/types';
import { api } from './api';
import { ErrorBox, Field, Heading, Load, Pager, useApi } from './ui';

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

const reasons: Record<string, string> = {
  GOAL: 'Chiếm ô mục tiêu',
  WIPEOUT: 'Ăn hết quân',
  STALEMATE: 'Hết nước đi',
  MOVE_LIMIT: 'Phân định sau 300 nước',
  RESIGNED: 'Đầu hàng',
};
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

export function CasualPlay() {
  const { id } = useParams<{ id: string }>();
  const query = useApi('getCasualGame', { path: { id: id! } }, !!id, 5000);
  const cache = useQueryClient();
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(),
    [confirm, setConfirm] = useState(false);
  useEffect(() => {
    setError(undefined);
    setConfirm(false);
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
    }
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
              <p>
                Mỗi lượt đi một ô theo tám hướng. Không đi vào ô có quân mình hoặc quân đối phương mà bạn
                không ăn được.
              </p>
              <p>Xanh cần chiếm i9; Đỏ cần chiếm a1. Không được đi vào ô mục tiêu của đối thủ.</p>
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
    </>
  );
}
