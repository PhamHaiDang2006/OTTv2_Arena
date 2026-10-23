import { ownerOf } from '@ottv2/replay-viewer';
import type { Side } from '../../contracts/viewer-api';
import { PieceIcon } from './casual-presentation';
import { cells, mapGoals, type Position, type Move } from './special-engine';

/** Four concentric rows, 24 sectors. The last sector shares an edge with the first. */
export function CircularBoard({
  position,
  side,
  selected,
  targets,
  last,
  onCell,
}: {
  position: Position;
  side: Side;
  selected?: string;
  targets: string[];
  last?: Move;
  onCell?: (id: string) => void;
}) {
  const point = (radius: number, angle: number) => [
    240 + radius * Math.cos(angle),
    240 + radius * Math.sin(angle),
  ];
  const goals = mapGoals('circular');
  return (
    <svg
      className="circular-board"
      viewBox="0 0 480 480"
      role={onCell ? 'group' : 'img'}
      aria-label="Bàn Vành khuyên"
    >
      <circle className="ring-rim" cx="240" cy="240" r="224" />
      {cells('circular').map((c) => {
        const angle = (c.q * Math.PI) / 12 - Math.PI / 2 + (side === 'RED' ? Math.PI : 0);
        const inner = 96 + c.r * 31,
          outer = inner + 31;
        const a = angle - Math.PI / 24,
          b = angle + Math.PI / 24;
        const p1 = point(inner, a),
          p2 = point(outer, a),
          p3 = point(outer, b),
          p4 = point(inner, b);
        const [x, y] = point((inner + outer) / 2, angle);
        const piece = position[c.id],
          goal = c.id === goals.BLUE ? 'BLUE' : c.id === goals.RED ? 'RED' : null;
        const label = `Ô ${c.id}: ${piece ? `${ownerOf(piece) === 'BLUE' ? 'Xanh' : 'Đỏ'} ${{ B: 'búa', P: 'bao', K: 'kéo' }[piece.toUpperCase()]}` : 'trống'}${goal ? `, đích ${goal === 'BLUE' ? 'Xanh' : 'Đỏ'}` : ''}`;
        return (
          <g
            key={c.id}
            role={onCell ? 'button' : undefined}
            tabIndex={onCell ? 0 : undefined}
            aria-label={onCell ? label : undefined}
            aria-pressed={onCell ? selected === c.id : undefined}
            className={`ring-cell ${(c.q + c.r) % 2 ? 'alternate' : ''} ${selected === c.id ? 'selected' : ''} ${targets.includes(c.id) ? 'target' : ''} ${last?.from === c.id || last?.to === c.id ? 'last' : ''}`}
            onClick={() => onCell?.(c.id)}
            onKeyDown={(e) => {
              if (onCell && (e.key === 'Enter' || e.key === ' ')) {
                e.preventDefault();
                onCell(c.id);
              }
            }}
          >
            <path
              className="ring-tile"
              d={`M${p1} L${p2} A${outer},${outer} 0 0 1 ${p3} L${p4} A${inner},${inner} 0 0 0 ${p1} Z`}
            />
            {goal && (
              <path
                className={`ring-flag ${goal}`}
                transform={`translate(${x - 7},${y - 9})`}
                d="M0 20V0M0 1H14L10 6L14 11H0"
              />
            )}
            {piece && (
              <g className={`ring-piece ${ownerOf(piece)}`}>
                <circle cx={x} cy={y} r="12" />
                <svg x={x - 9} y={y - 9} width="18" height="18" viewBox="0 0 48 48">
                  <PieceIcon piece={piece} />
                </svg>
              </g>
            )}
            {targets.includes(c.id) && <circle className="ring-dot" cx={x + 9} cy={y + 9} r="3" />}
          </g>
        );
      })}
      <circle className="ring-center" cx="240" cy="240" r="94" />
      <text className="ring-center-label" x="240" y="238" textAnchor="middle">
        OTT v2
      </text>
      <text className="ring-center-small" x="240" y="258" textAnchor="middle">
        VÀNH KHUYÊN
      </text>
    </svg>
  );
}
