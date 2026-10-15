"""Validate local schemas, OpenAPI, fixture coverage and semantic wire invariants.

Run: python contracts/validate.py
Dependencies: python -m pip install --target contracts/.deps -r contracts/requirements.txt
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / '.deps'))
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from openapi_spec_validator import validate_spec


def read(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


COMMON = read('schemas/common.schema.json')
REGISTRY = Registry().with_resources(
    (p.as_uri(), Resource.from_contents(json.loads(p.read_text(encoding='utf-8'))))
    for p in (ROOT / 'schemas').glob('*.json')
)


def validator(definition=None, schema=None):
    if definition:
        document = {'$ref': f'{(ROOT / "schemas/common.schema.json").as_uri()}#/$defs/{definition}'}
    else:
        document = {'$ref': (ROOT / schema).as_uri()}
    return Draft202012Validator(document, registry=REGISTRY, format_checker=FormatChecker())


def parse_fen(fen):
    rows = fen.split('/')
    if len(rows) != 9:
        raise ValueError('FEN must contain 9 ranks')
    board = []
    for row in reversed(rows):
        cells = []
        for c in row:
            if c in '123456789':
                cells.extend([None] * int(c))
            elif c in 'BPKbpk':
                cells.append(c)
            else:
                raise ValueError('Invalid FEN token')
        if len(cells) != 9:
            raise ValueError('FEN rank must expand to 9 cells')
        board.extend(cells)
    return board


def replay_errors(data):
    """Structural replay checks, not a replacement for the game referee."""
    errors = []
    try:
        board = parse_fen(data['initial_fen'])
    except (ValueError, KeyError) as exc:
        return [str(exc)]
    if data['result']['plies'] != len(data['moves']):
        errors.append('result.plies must equal moves.length')
    clocks = {'BLUE': 60000, 'RED': 60000}
    for i, move in enumerate(data['moves'], 1):
        expected = 'BLUE' if i % 2 else 'RED'
        if move['ply'] != i or move['side'] != expected:
            errors.append('Non-contiguous ply or incorrect side')
        source, target = move['move'][:2], move['move'][2:]
        index = lambda square: (int(square[1]) - 1) * 9 + ord(square[0]) - ord('a')
        a, b = index(source), index(target)
        piece = board[a]
        if a == b or piece is None or piece.isupper() != (move['side'] == 'BLUE'):
            errors.append('Invalid source piece')
        if board[b] != move['capture']:
            errors.append('Capture does not match board')
        if move['clock_ms'] > clocks[move['side']]:
            errors.append('Clock increased')
        clocks[move['side']] = move['clock_ms']
        board[b], board[a] = piece, None
    return errors


def semantic_errors(definition, data):
    if definition == 'Replay':
        return replay_errors(data)
    if definition == 'EngineResult':
        errors = replay_errors(data['replay'])
        if {k: data[k] for k in ('winner', 'reason', 'plies')} != data['replay']['result']:
            errors.append('EngineResult disagrees with replay')
        return errors
    if definition == 'MatchJob':
        return [f'config.{k} disagrees with job' for k in ('players', 'engine_version', 'map_id') if data[k] != data['config'][k]]
    if definition == 'GameConfig':
        try:
            parse_fen(data['initial_fen'])
        except ValueError as exc:
            return [str(exc)]
    return []


def main():
    errors = []
    for file in (ROOT / 'schemas').glob('*.json'):
        Draft202012Validator.check_schema(read(str(file.relative_to(ROOT))))
    api = read('openapi.yaml')  # JSON is a YAML 1.2 subset; no ambiguous YAML scalars.
    validate_spec(api)
    # Check every ref, including definitions not reached by a fixture.
    def walk(value, document):
        if isinstance(value, dict):
            if '$ref' in value:
                target = value['$ref']
                if not target.startswith('#/'):
                    raise AssertionError(f'Unexpected external ref in bundled document: {target}')
                resolved = document
                for part in target[2:].split('/'):
                    resolved = resolved[part.replace('~1', '/').replace('~0', '~')]
            for item in value.values():
                walk(item, document)
        elif isinstance(value, list):
            for item in value:
                walk(item, document)
    walk(COMMON, COMMON)
    walk(api, api)
    cases = read('examples/manifest.json')
    for case in cases:
        data = read(case['file'])
        definition = case.get('definition')
        if not definition:
            definition = read(case['schema'])['$ref'].split('/')[-1]
        failures = [e.message for e in validator(definition).iter_errors(data)]
        if not failures:
            failures.extend(semantic_errors(definition, data))
        if bool(failures) == case['valid']:
            errors.append(f'{case["file"]}: expected valid={case["valid"]}; {failures}')
    operations = read('operations.json')
    seen = set()
    for operation in operations:
        oid = operation['operationId']
        if oid in seen:
            errors.append(f'Duplicate operationId {oid}')
        seen.add(oid)
        spec = api['paths'][operation['path']][operation['method']]
        path_names = set(re.findall(r'\{(\w+)\}', operation['path']))
        if path_names != {p['name'] for p in spec['parameters'] if p['in'] == 'path' and p['required']}:
            errors.append(f'Path params mismatch: {oid}')
        for kind in ('request', 'response'):
            if operation[kind] and not operation.get(kind + '_example'):
                errors.append(f'Missing {kind} fixture: {oid}')
    if len(operations) != sum(len(item) for item in api['paths'].values()):
        errors.append('Operations index does not cover OpenAPI')
    board_cases = read('fixtures/board-cases.json')['cases']
    for case in board_cases:
        board = parse_fen(case['initial_fen'])
        expected = parse_fen(case['expected_fen'])
        if case['legal']:
            index = lambda square: (int(square[1]) - 1) * 9 + ord(square[0]) - ord('a')
            a, b = index(case['move'][:2]), index(case['move'][2:])
            board[b], board[a] = board[a], None
        if board != expected:
            errors.append(f'Board fixture final position mismatch: {case["id"]}')
    # Independently check generated draw vectors using Python integer masking.
    for case in read('fixtures/draw-cases.json')['cases']:
        state = case['seed']
        groups = {label: [] for label in 'ABCD'}
        def bounded(bound):
            nonlocal state
            limit = (2**32 // bound) * bound
            while True:
                state ^= (state << 13) & 0xffffffff
                state ^= state >> 17
                state ^= (state << 5) & 0xffffffff
                if state < limit:
                    return state % bound
        for start in range(1, case['team_count'] + 1, 4):
            pot = list(range(start, start + 4))
            for i in range(3, 0, -1):
                j = bounded(i + 1)
                pot[i], pot[j] = pot[j], pot[i]
            for label, team in zip('ABCD', pot):
                groups[label].append(team)
        if groups != case['groups']:
            errors.append('Draw vector mismatch')
    if errors:
        print('\n'.join(errors))
        return 1
    print(f'PASS: OpenAPI 3.1, {len(COMMON["$defs"])} definitions, {len(operations)} operations, {len(cases)} positive/negative cases; refs, replay invariants, {len(board_cases)} board cases, draw vectors.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
