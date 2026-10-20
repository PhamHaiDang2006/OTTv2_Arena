import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import operations from '../../contracts/operations.json';
import { validate } from '../shared/schema';
describe('HTTP producer fixtures accepted by frontend runtime validators', () => {
  for (const operation of operations) {
    if (operation.response && operation.response_example)
      it(operation.operationId, () => {
        const data = JSON.parse(readFileSync(resolve('../contracts', operation.response_example!), 'utf8'));
        expect(validate(operation.response!, data)).toEqual(data);
      });
  }
  it('rejects corrupt replay', () => {
    expect(() => validate('Replay', { format: 2 })).toThrow();
  });
});
