import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import type { Room, RoomCommand, RoomMap, User } from '../../contracts/generated/types';
import { api } from './api';
import { CasualBoard } from './casual';
import { SpecialBoard } from './special';
import { ErrorBox, Heading } from './ui';
import './rooms.css';
import { PlayerIdentity } from './profile';

export const roomMapNames = { standard: 'Casual · 9 × 9', hexagon: 'Hexagon', circular: 'Annulus' };
const reasons = {
  GOAL: 'Đã tới đích',
  WIPEOUT: 'Đối thủ hết quân',
  STALEMATE: 'Đối thủ hết nước đi',
  MOVE_LIMIT: 'Đạt giới hạn 300 nước',
  RESIGNED: 'Đối thủ đầu hàng hoặc rời phòng',
};
const labels = { waiting: 'Chờ sẵn sàng', playing: 'Đang chơi', finished: 'Đã kết thúc', closed: 'Đã đóng' };

export function RoomsLobby({ user }: { user: User }) {
  const navigate = useNavigate();
  const [search] = useSearchParams();
  const [code, setCode] = useState(search.get('invite')?.toUpperCase() ?? '');
  const [map, setMap] = useState<RoomMap>('standard');
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>();
  const gate = useRef(false);
  const rooms = useQuery({
    queryKey: ['rooms', user.id],
    queryFn: () => api('listRooms', undefined),
    refetchOnMount: 'always',
  });
  async function enter(join: boolean) {
    if (gate.current) return;
    gate.current = true;
    setBusy(true);
    setError(undefined);
    try {
      const room = join
        ? await api('joinRoom', { code: code.trim().toUpperCase() })
        : await api('createRoom', { map });
      navigate(`/rooms/${room.id}`);
    } catch (e) {
      setError(e);
    } finally {
      gate.current = false;
      setBusy(false);
    }
  }
  return (
    <section className="room-lobby">
      <Heading
        eyebrow="OTT v2 / CHƠI VỚI BẠN"
        title="Một bàn cờ. Hai người bạn."
        description="Tạo phòng riêng, gửi lời mời và cùng chơi. Không cần nộp bot hay chờ duyệt đội."
      />
      <div className="room-forms">
        <form
          className="card"
          onSubmit={(e) => {
            e.preventDefault();
            void enter(false);
          }}
        >
          <h2>Tạo phòng</h2>
          <label>
            Bản đồ
            <select value={map} onChange={(e) => setMap(e.target.value as RoomMap)}>
              {Object.entries(roomMapNames).map(([id, name]) => (
                <option key={id} value={id}>
                  {name}
                </option>
              ))}
            </select>
          </label>
          <p>Hai người cùng sẵn sàng để bắt đầu. Quân xanh đi trước.</p>
          <button className="primary" disabled={busy}>
            Tạo phòng hai người
          </button>
        </form>
        <form
          className="card"
          onSubmit={(e) => {
            e.preventDefault();
            void enter(true);
          }}
        >
          <h2>Vào phòng của bạn</h2>
          <label>
            Mã mời
            <input
              value={code}
              maxLength={8}
              pattern="[A-Za-z2-9]{8}"
              required
              autoComplete="off"
              onChange={(e) => setCode(e.target.value.toUpperCase())}
              placeholder="ABCDEFGH"
            />
          </label>
          <p>Dùng mã 8 ký tự hoặc mở link mời từ người tạo phòng.</p>
          <button className="primary" disabled={busy}>
            Vào phòng
          </button>
        </form>
      </div>
      <ErrorBox error={error ?? rooms.error} />
      <h2>Phòng gần đây</h2>
      <p>Vào lại bằng cùng tài khoản để tiếp tục ván đang chơi.</p>
      {rooms.isLoading ? (
        <p>Đang tải phòng…</p>
      ) : !rooms.data?.length ? (
        <p>Bạn chưa có phòng nào.</p>
      ) : (
        <div className="room-list">
          {rooms.data.map((r) => (
            <Link className="card" key={r.id} to={`/rooms/${r.id}`}>
              <strong>{roomMapNames[r.map]}</strong>
              <span>
                {r.code} · {labels[r.status]} · Ván {r.round}
              </span>
            </Link>
          ))}
        </div>
      )}
    </section>
  );
}

export function RoomPage({ user }: { user: User }) {
  const { id = '' } = useParams();
  return <RoomMatch key={`${user.id}:${id}`} id={id} user={user} />;
}

function RoomMatch({ id, user }: { id: string; user: User }) {
  const cache = useQueryClient();
  const queryKey = ['room', user.id, id];
  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => api('getRoom', undefined, { path: { room_id: id }, signal }),
    refetchInterval: 2000,
    refetchOnMount: 'always',
    refetchOnWindowFocus: 'always',
    refetchOnReconnect: 'always',
    retry: false,
  });
  const [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>();
  const [online, setOnline] = useState(navigator.onLine),
    [selected, setSelected] = useState<string>();
  const [copied, setCopied] = useState(false),
    [confirm, setConfirm] = useState<'resign' | 'leave'>();
  const gate = useRef(false);
  useEffect(() => {
    const update = () => {
      setOnline(navigator.onLine);
      if (navigator.onLine) void query.refetch();
    };
    window.addEventListener('online', update);
    window.addEventListener('offline', update);
    return () => {
      window.removeEventListener('online', update);
      window.removeEventListener('offline', update);
    };
  }, [id]);
  useEffect(() => {
    setSelected(undefined);
  }, [query.data?.revision]);
  async function command(action: RoomCommand['action'], move?: RoomCommand['move']) {
    if (!query.data || gate.current || !online || query.isError) return;
    gate.current = true;
    setBusy(true);
    setError(undefined);
    setConfirm(undefined);
    try {
      // Stop an older poll before publishing the authoritative command result.
      await cache.cancelQueries({ queryKey });
      const next = await api(
        'roomCommand',
        { revision: query.data.revision, action, ...(move ? { move } : {}) },
        { path: { room_id: id } },
      );
      cache.setQueryData<Room>(queryKey, (old) => (!old || next.revision >= old.revision ? next : old));
    } catch (e) {
      setError(e);
    } finally {
      await query.refetch();
      gate.current = false;
      setBusy(false);
    }
  }
  const room = query.data;
  if (!room)
    return (
      <>
        <Link to="/rooms">← Phòng hai người</Link>
        <ErrorBox error={query.error} />
        <p role="status">
          {query.isError ? 'Không thể tải phòng. Kiểm tra kết nối và tài khoản.' : 'Đang vào phòng…'}
        </p>
        <button onClick={() => void query.refetch()}>Thử lại</button>
      </>
    );
  const me = room.players.find((p) => p.id === user.id);
  if (!me) return <p>Bạn không có ghế trong phòng này.</p>;
  const opponent = room.players.find((p) => p.id !== user.id);
  const connected = online && !query.isError;
  const canMove = connected && !busy && room.status === 'playing' && room.turn === me.side;
  const moves = canMove ? room.legal_moves : [];
  const invitation = new URL(`/rooms?invite=${room.code}`, window.location.origin).href;
  const turnText =
    room.status === 'playing'
      ? room.turn === me.side
        ? 'Lượt của bạn'
        : 'Đang chờ đối thủ'
      : labels[room.status];
  return (
    <section className="room-match">
      <div className="room-toolbar">
        <Link to="/rooms">← Danh sách phòng</Link>
        <span role="status">
          {connected
            ? 'Đã đồng bộ · cập nhật mỗi 2 giây'
            : 'Mất kết nối · đang kết nối lại, ván vẫn được giữ'}
        </span>
      </div>
      <Heading
        eyebrow="OTT v2 / PHÒNG HAI NGƯỜI"
        title={`${roomMapNames[room.map]} · Phòng ${room.code}`}
        description={`Ván ${room.round} · ${room.moves.length} nước · Bạn cầm quân ${me.side === 'BLUE' ? 'xanh' : 'đỏ'}`}
      />
      <div className="room-invite">
        <label>
          Link mời
          <input readOnly value={invitation} onFocus={(e) => e.target.select()} />
        </label>
        <button
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(invitation);
              setCopied(true);
            } catch {
              setError(new Error('Hãy chọn và sao chép link trong ô bên cạnh.'));
            }
          }}
        >
          {copied ? 'Đã sao chép' : 'Sao chép lời mời'}
        </button>
      </div>
      <ErrorBox error={error ?? query.error} />
      <div className="room-layout">
        <div className="room-table">
          <div className={`room-player ${opponent?.side ?? 'RED'}`}>
            {opponent ? <PlayerIdentity id={opponent.id} /> : <strong>Ghế còn trống</strong>}
            <span>
              {opponent
                ? room.status === 'waiting'
                  ? opponent.ready
                    ? 'Đã sẵn sàng'
                    : 'Chưa sẵn sàng'
                  : opponent.rematch
                    ? 'Muốn chơi lại'
                    : 'Đã tham gia'
                : 'Gửi mã hoặc link mời bạn'}
            </span>
          </div>
          <p className="room-turn" aria-live="polite">
            {turnText}
          </p>
          {room.map === 'standard' ? (
            <CasualBoard
              busy={!canMove}
              onMove={(m) => void command('move', { from: m.slice(0, 2), to: m.slice(2) })}
              game={{
                id: `${room.id}:${room.round}`,
                fen: room.fen!,
                human_side: me.side,
                bot: 'random',
                status: room.status === 'playing' ? 'playing' : 'finished',
                ply: room.moves.length,
                turn: room.turn,
                legal_moves: moves.map((m) => m.from + m.to),
                moves: room.moves.map((m, i) => ({
                  side: i % 2 ? 'RED' : 'BLUE',
                  move: m.from + m.to,
                  capture: null,
                })),
                winner: room.result?.winner ?? null,
                reason: room.result?.reason ?? null,
                created_at: '',
              }}
            />
          ) : (
            <SpecialBoard
              map={room.map}
              position={room.position}
              side={me.side}
              selected={selected}
              targets={moves.filter((m) => m.from === selected).map((m) => m.to)}
              last={room.moves.at(-1)}
              onCell={
                canMove
                  ? (cell) => {
                      const move = moves.find((m) => m.from === selected && m.to === cell);
                      if (move) void command('move', move);
                      else setSelected(moves.some((m) => m.from === cell) ? cell : undefined);
                    }
                  : undefined
              }
            />
          )}
          <div className={`room-player ${me.side}`}>
            <PlayerIdentity id={me.id} />
            <strong>Bạn · {me.side === 'BLUE' ? 'Xanh' : 'Đỏ'}</strong>
            <span>{me.ready ? 'Đã sẵn sàng' : 'Đã tham gia'}</span>
          </div>
        </div>
        <aside className="card room-controls">
          <h2>
            {room.result
              ? room.result.winner === me.side
                ? 'Bạn đã thắng!'
                : 'Ván đấu kết thúc'
              : 'Cùng vào trận'}
          </h2>
          {room.result && (
            <p>
              {reasons[room.result.reason]} · {room.moves.length} nước
            </p>
          )}
          {room.status === 'waiting' && (
            <>
              <p>Ván bắt đầu khi cả hai sẵn sàng. Xanh đi trước.</p>
              <button
                className="primary"
                disabled={busy || !connected}
                onClick={() => void command(me.ready ? 'unready' : 'ready')}
              >
                {me.ready ? 'Hủy sẵn sàng' : 'Sẵn sàng'}
              </button>
            </>
          )}
          {room.status === 'finished' && (
            <>
              <p>Chơi lại sẽ đổi màu quân. Cần cả hai đồng ý.</p>
              <button
                className="primary"
                disabled={busy || !connected || me.rematch}
                onClick={() => void command('rematch')}
              >
                {me.rematch ? 'Đợi bạn đồng ý chơi lại…' : 'Chơi lại'}
              </button>
            </>
          )}
          {room.status === 'playing' && (
            <button disabled={busy || !connected} onClick={() => setConfirm('resign')}>
              Đầu hàng
            </button>
          )}
          {room.status !== 'closed' && (
            <button disabled={busy || !connected} onClick={() => setConfirm('leave')}>
              Rời và đóng phòng
            </button>
          )}
          {confirm && (
            <div role="alert">
              <p>
                {confirm === 'leave'
                  ? 'Đóng phòng cho cả hai? Nếu đang chơi, bạn sẽ thua ván này.'
                  : 'Bạn chắc chắn muốn đầu hàng?'}
              </p>
              <button disabled={busy} onClick={() => void command(confirm)}>
                Xác nhận
              </button>
              <button onClick={() => setConfirm(undefined)}>Hủy</button>
            </div>
          )}
          <p>Đóng tab không tính là đầu hàng. Mở lại phòng bằng cùng tài khoản để tiếp tục.</p>
          <details>
            <summary>Lịch sử · {room.moves.length} nước</summary>
            <ol className="room-history">
              {room.moves.map((m, i) => (
                <li key={i}>
                  {i % 2 ? 'Đỏ' : 'Xanh'}: {m.from} → {m.to}
                </li>
              ))}
            </ol>
          </details>
        </aside>
      </div>
    </section>
  );
}
