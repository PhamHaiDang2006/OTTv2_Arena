import { expect, it } from 'vitest';
import vectors from '../../contracts/fixtures/room-games.json';
import { initialPosition, moved, movesFor, resultFor, type MapId } from '../src/special-engine';

it.each(vectors)('server and browser agree on a complete $map game', (vector) => {
  const map = vector.map as MapId;
  let position = initialPosition(map);
  expect(position).toEqual(vector.initial);
  let result = null;
  for (const [index, move] of vector.moves.entries()) {
    const side = index % 2 ? 'RED' : 'BLUE';
    expect(result).toBeNull();
    expect(movesFor(map, position, side)).toContainEqual(move);
    position = moved(position, move);
    result = resultFor(map, position, side, index + 1);
  }
  expect(position).toEqual(vector.position);
  expect(result).toEqual(vector.result);
});
