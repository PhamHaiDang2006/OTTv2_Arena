import Ajv from 'ajv/dist/2020';
import addFormats from 'ajv-formats';
import common from '../../contracts/schemas/common.schema.json';
const ajv = new Ajv({ strict: false });
addFormats(ajv);
ajv.addSchema(common, 'common');
export function validate<T>(name: string, value: unknown): T {
  const check = ajv.getSchema(`common#/$defs/${name}`);
  if (!check || !check(value)) throw new Error(`Dữ liệu ${name} không đúng hợp đồng 1.0.0.`);
  return value as T;
}
