import { useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { ownerOf } from '@ottv2/replay-viewer';
import type { Side, User } from '../../contracts/generated/types';
import type { CasualBot } from './casual-engine';
import { PieceIcon } from './casual-presentation';
import { ErrorBox, Heading } from './ui';
import {
  cells,
  frame,
  goals,
  initialPosition,
  listSpecial,
  mapNames,
  movesFor,
  newSpecial,
  playSpecial,
  readSpecial,
  storeSpecial,
  type MapId,
  type Position,
  type SpecialGame,
} from './special-engine';
import './special.css';
import { CircularBoard } from './circular-board';

const botNames = { random: 'Dễ', greedy: 'Trung bình', hard: 'Khó' };
const reasons = {
  GOAL: 'Đã tới đích',
  WIPEOUT: 'Đối thủ hết quân',
  STALEMATE: 'Đối thủ không còn nước đi',
  MOVE_LIMIT: 'Đủ 300 nước — phân định theo đội hình, quân số rồi khoảng cách đến đích',
  RESIGNED: 'Đầu hàng',
};
export function SpecialBoard({
  map,
  position,
  side = 'BLUE',
  selected,
  targets = [],
  last,
  onCell,
}: {
  map: MapId;
  position: Position;
  side?: Side;
  selected?: string;
  targets?: string[];
  last?: { from: string; to: string };
  onCell?: (id: string) => void;
}) {
  if (map === 'circular') return <CircularBoard {...{ position, side, selected, targets, last, onCell }} />;
  return (
    <div className="special-board" role={onCell ? 'group' : 'img'} aria-label={`Bàn ${mapNames[map]}`}>
      {cells(map).map((c) => {
        const direction = side === 'BLUE' ? 1 : -1;
        const x = 50 + direction * c.q * 7.8,
          y = 50 + direction * (c.r + c.q / 2) * 9;
        const piece = position[c.id],
          goal = c.id === goals.BLUE ? 'BLUE' : c.id === goals.RED ? 'RED' : null;
        const label = `Ô ${c.id}: ${piece ? `${ownerOf(piece) === 'BLUE' ? 'Xanh' : 'Đỏ'} ${{ B: 'búa', P: 'bao', K: 'kéo' }[piece.toUpperCase()]}` : 'trống'}${goal ? `, đích ${goal === 'BLUE' ? 'Xanh' : 'Đỏ'}` : ''}`;
        const content = (
          <>
            {goal && (
              <svg className={`hex-goal ${goal}`} viewBox="0 0 24 24" aria-hidden="true">
                <path
                  d="M5 22V3m0 1c5-5 9 5 15 0v11c-6 5-10-5-15 0"
                  fill="currentColor"
                  stroke="currentColor"
                  strokeWidth="2"
                />
              </svg>
            )}
            {piece && (
              <span className={`hex-token ${ownerOf(piece)}`}>
                <PieceIcon piece={piece} />
              </span>
            )}
            {targets.includes(c.id) && (
              <span className="hex-target" aria-hidden="true">
                •
              </span>
            )}
          </>
        );
        const props = {
          className: `hex-cell tone-${(((c.q - c.r) % 3) + 3) % 3} ${selected === c.id ? 'selected' : ''} ${targets.includes(c.id) ? 'target' : ''} ${last?.from === c.id || last?.to === c.id ? 'last' : ''}`,
          style: { left: `${x}%`, top: `${y}%` },
        };
        return onCell ? (
          <button
            key={c.id}
            {...props}
            aria-label={label}
            aria-pressed={selected === c.id}
            onClick={() => onCell(c.id)}
          >
            {content}
          </button>
        ) : (
          <span key={c.id} {...props} aria-hidden="true">
            {content}
          </span>
        );
      })}
    </div>
  );
}
function Rules() {
  return (
    <details className="card special-rules">
      <summary>Luật Bản đồ đặc biệt · special-v1</summary>
      <p>
        Hexagon: đi 1 ô theo 6 cạnh. Vành khuyên: đi 1 ô dọc vòng, vào/ra một vòng hoặc chéo một ô (tối đa 8
        hướng). Búa ăn Kéo · Kéo ăn Bao · Bao ăn Búa. Mỗi phe có 12 quân (4 mỗi loại). Xanh đi trước.
      </p>
      <p>
        Đưa quân tới lá cờ mang màu phe mình ở phía đối diện để thắng. Không được đứng trên đích của đối thủ.
        Cũng thắng khi đối thủ hết quân hoặc hết nước hợp lệ.
      </p>
      <p>
        Vành khuyên gồm 4 vòng đồng tâm × 24 ô hình quạt. Ô 23 nối ô 0 trên cùng vòng; không đi xuyên tâm hoặc
        vượt mép trong/ngoài. Màu nền ô chỉ để dễ nhìn. Ván cũ có nhãn “hex” giữ luật sáu cạnh ban đầu.
      </p>
      <p>
        Tối đa 300 nước. Phân định lần lượt: số quân của loại ít nhất, tổng quân, khoảng cách đường đi ngắn
        nhất đến đích; hòa hoàn toàn thì Đỏ thắng. Đây là luật thử nghiệm riêng, không dùng cho Arena.
      </p>
    </details>
  );
}
export function SpecialLobby({ user }: { user: User }) {
  const navigate = useNavigate();
  const [map, setMap] = useState<MapId>('hexagon'),
    [bot, setBot] = useState<CasualBot>('greedy'),
    [side, setSide] = useState<Side>('BLUE');
  const [games, setGames] = useState<SpecialGame[]>([]),
    [error, setError] = useState<unknown>(),
    [busy, setBusy] = useState(false);
  const pending = useRef(false);
  useEffect(() => {
    const reload = () => {
      try {
        setGames(listSpecial(user.id));
      } catch (e) {
        setError(e);
      }
    };
    reload();
    window.addEventListener('storage', reload);
    return () => window.removeEventListener('storage', reload);
  }, [user.id]);
  return (
    <div className="special-page">
      <Heading
        eyebrow="OTT v2 / KHÁM PHÁ"
        title="Bản đồ đặc biệt"
        description="Cùng búa, bao, kéo. Hai hình dạng bàn cờ, những đường tấn công mới."
      />
      <div className="special-maps">
        {(['hexagon', 'circular'] as const).map((id) => (
          <button
            type="button"
            className={`card special-map ${map === id ? 'active' : ''}`}
            key={id}
            aria-pressed={map === id}
            onClick={() => setMap(id)}
          >
            <SpecialBoard map={id} position={initialPosition(id)} />
            <strong>{mapNames[id]}</strong>
            <span>{id === 'hexagon' ? '91 ô · Sáu hướng tiếp cận' : '96 ô · 4 vòng đồng tâm'}</span>
          </button>
        ))}
      </div>
      <form
        className="card special-controls"
        onSubmit={async (e) => {
          e.preventDefault();
          if (pending.current) return;
          pending.current = true;
          setBusy(true);
          setError(undefined);
          try {
            const g = newSpecial(map, side, bot);
            await storeSpecial(user.id, g);
            navigate(`/special/${g.id}`);
          } catch (e) {
            setError(e);
          } finally {
            pending.current = false;
            setBusy(false);
          }
        }}
      >
        <label>
          Độ khó
          <select value={bot} onChange={(e) => setBot(e.target.value as CasualBot)}>
            {Object.entries(botNames).map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Màu quân
          <select value={side} onChange={(e) => setSide(e.target.value as Side)}>
            <option value="BLUE">Xanh · Đi trước</option>
            <option value="RED">Đỏ · Đi sau</option>
          </select>
        </label>
        <button className="primary" disabled={busy}>
          {busy ? 'Đang tạo…' : `Chơi ${mapNames[map]}`}
        </button>
      </form>
      <ErrorBox error={error} />
      <Rules />
      <h2>Ván trên trình duyệt này</h2>
      <p className="muted">
        Ván và bot chạy trên máy bạn, lưu riêng theo tài khoản. Không đồng bộ sang thiết bị khác.
      </p>
      {!games.length ? (
        <p>Chọn bản đồ để bắt đầu ván đầu tiên.</p>
      ) : (
        <div className="special-history">
          {games.map((g) => (
            <Link className="card" key={g.id} to={`/special/${g.id}`}>
              <strong>
                {mapNames[g.map]} · {botNames[g.bot]}
              </strong>
              <span>
                {g.moves.length} nước · {frame(g).result ? 'Đã kết thúc' : 'Chơi tiếp'} ·{' '}
                {new Date(g.created).toLocaleString('vi-VN')}
              </span>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
export function SpecialPlay({ user }: { user: User }) {
  const { id = '' } = useParams();
  return <SpecialMatch key={`${user.id}:${id}`} user={user} id={id} />;
}
function SpecialMatch({ user, id }: { user: User; id: string }) {
  const navigate = useNavigate(),
    pending = useRef(false),
    mounted = useRef(true);
  const [game, setGame] = useState<SpecialGame | null>(null),
    [error, setError] = useState<unknown>();
  const [selected, setSelected] = useState<string>(),
    [busy, setBusy] = useState(false),
    [review, setReview] = useState<number | null>(null),
    [confirm, setConfirm] = useState(false);
  useEffect(() => {
    mounted.current = true;
    const reload = () => {
      try {
        setGame(readSpecial(user.id, id));
        setSelected(undefined);
        setReview(null);
      } catch (e) {
        setError(e);
      }
    };
    reload();
    window.addEventListener('storage', reload);
    return () => {
      mounted.current = false;
      window.removeEventListener('storage', reload);
    };
  }, [user.id, id]);
  if (!game)
    return (
      <div className="card">
        <h1>Không tìm thấy ván trên trình duyệt này</h1>
        <ErrorBox error={error} />
        <Link to="/special">Về sảnh Bản đồ đặc biệt</Link>
      </div>
    );
  const current = frame(game),
    shown = frame(game, review ?? game.moves.length);
  const legal = movesFor(game.map, current.position, game.human),
    targets = legal.filter((m) => m.from === selected).map((m) => m.to);
  const count = review ?? game.moves.length;
  const change = async (update: () => SpecialGame) => {
    if (pending.current) return;
    pending.current = true;
    setBusy(true);
    setError(undefined);
    setSelected(undefined);
    // Yield for the thinking indicator; calculation is bounded to two plies.
    await new Promise<void>((resolve) => window.setTimeout(resolve, 30));
    try {
      if (!mounted.current) return;
      const next = update();
      await storeSpecial(user.id, next, game);
      if (mounted.current) {
        setGame(next);
        setReview(null);
        setConfirm(false);
      }
    } catch (e) {
      if (mounted.current) setError(e);
    } finally {
      pending.current = false;
      if (mounted.current) setBusy(false);
    }
  };
  const onCell = (cell: string) => {
    if (busy || current.result || review !== null) return;
    if (selected && targets.includes(cell)) {
      void change(() => playSpecial(game, { from: selected, to: cell }));
      return;
    }
    setSelected(current.position[cell] && ownerOf(current.position[cell]) === game.human ? cell : undefined);
  };
  return (
    <div className="special-page">
      <Link to="/special">← Bản đồ đặc biệt</Link>
      <Heading
        eyebrow="SPECIAL-v1 / CHƠI TRÊN TRÌNH DUYỆT"
        title={mapNames[game.map]}
        description={`Bot ${botNames[game.bot]} · Bạn cầm quân ${game.human === 'BLUE' ? 'Xanh' : 'Đỏ'}`}
      />
      <ErrorBox error={error} />
      <div className="special-match">
        <section className="card special-board-panel">
          <div className="special-player">
            Máy · {Object.values(shown.position).filter((p) => ownerOf(p) !== game.human).length} quân
          </div>
          <p className="special-status" role="status">
            {review !== null
              ? `Xem lại · Nước ${count}`
              : busy
                ? 'Máy đang tính…'
                : current.result
                  ? current.result.winner === game.human
                    ? 'Bạn thắng!'
                    : 'Máy thắng'
                  : 'Lượt của bạn · Chọn quân rồi chọn ô sáng'}
          </p>
          <SpecialBoard
            map={game.map}
            position={shown.position}
            side={game.human}
            selected={selected}
            targets={busy || review !== null ? [] : targets}
            last={game.moves[count - 1]}
            onCell={onCell}
          />
          <div className="special-player">
            Bạn · {Object.values(shown.position).filter((p) => ownerOf(p) === game.human).length} quân ·{' '}
            {game.human === 'BLUE' ? 'Xanh' : 'Đỏ'}
          </div>
        </section>
        <aside className="special-tools">
          {current.result && (
            <section className="card">
              <h2>{current.result.winner === game.human ? 'Chiến thắng' : 'Ván đã kết thúc'}</h2>
              <p>{reasons[current.result.reason]}</p>
              <p>{game.moves.length} nước</p>
              <button
                disabled={busy}
                onClick={async () => {
                  if (pending.current) return;
                  pending.current = true;
                  setBusy(true);
                  try {
                    const next = newSpecial(game.map, game.human, game.bot);
                    await storeSpecial(user.id, next);
                    navigate(`/special/${next.id}`);
                  } catch (e) {
                    setError(e);
                  } finally {
                    pending.current = false;
                    setBusy(false);
                  }
                }}
              >
                Chơi lại
              </button>{' '}
              <Link to="/special">Về sảnh</Link>
            </section>
          )}
          <section className="card">
            <h2>Lịch sử · {game.moves.length} nước</h2>
            <label>
              Xem lại ván
              <input
                aria-label="Nước xem lại"
                type="range"
                min="0"
                max={game.moves.length}
                value={count}
                disabled={busy}
                onChange={(e) => {
                  setReview(Number(e.target.value));
                  setSelected(undefined);
                }}
              />
            </label>
            <button
              disabled={busy}
              onClick={() => {
                setReview(null);
                setSelected(undefined);
              }}
            >
              Về nước hiện tại
            </button>
            <ol className="special-moves">
              {game.moves.map((m, i) => (
                <li key={i}>
                  <button
                    disabled={busy}
                    aria-current={count === i + 1 ? 'step' : undefined}
                    onClick={() => {
                      setReview(i + 1);
                      setSelected(undefined);
                    }}
                  >
                    {i % 2 === 0 ? 'Xanh' : 'Đỏ'}: {m.from} → {m.to}
                  </button>
                </li>
              ))}
            </ol>
          </section>
          <Rules />
          {!current.result && (
            <section className="card">
              {confirm ? (
                <>
                  <p>Kết thúc ván và nhận thua?</p>
                  <button disabled={busy} onClick={() => void change(() => ({ ...game, resigned: true }))}>
                    Xác nhận đầu hàng
                  </button>
                  <button onClick={() => setConfirm(false)}>Tiếp tục chơi</button>
                </>
              ) : (
                <button disabled={busy} onClick={() => setConfirm(true)}>
                  Đầu hàng
                </button>
              )}
            </section>
          )}
        </aside>
      </div>
    </div>
  );
}
