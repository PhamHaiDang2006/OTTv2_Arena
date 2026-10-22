import copy
import json
import subprocess
import unittest
from pathlib import Path

from infra.check_resources import MIB, validate


def layout():
    common = {'cpuset': '6-7', 'cpus': '0.5', 'mem_limit': 512 * MIB,
              'memswap_limit': 512 * MIB, 'pids_limit': 128}
    services = {'registry': {**common, 'command': None, 'mem_limit': 256 * MIB, 'memswap_limit': 256 * MIB}}
    services['build-worker'] = {**common, 'command': ['ottv2-runner-worker', '--queue', 'build'],
                                'environment': {'RUNNER_CPUSET_BUILD': '6-7'}}
    for i in range(4):
        services[f'match-{i}'] = {**common,
            'command': ['ottv2-runner-worker', '--queue', 'match:tournament' if i < 3 else 'match:scrimmage'],
            'environment': {'RUNNER_CPUSET_BLUE': str(i * 2), 'RUNNER_CPUSET_RED': str(i * 2 + 1)}}
    return {'services': services}


class ResourceTests(unittest.TestCase):
    def test_rendered_compose_layouts(self):
        root = Path(__file__).resolve().parents[2]
        for env, files, cpu_count, expected_mib in [
            ('vps2.env.example', ['docker-compose.vps2.yml'], 8, 9472),
            ('.env.example', ['docker-compose.dev.yml', 'docker-compose.play.yml'], 4, 6400),
        ]:
            command = ['docker', 'compose', '--env-file', str(root / 'infra' / env)]
            for file in files:
                command += ['-f', str(root / 'infra' / file)]
            config = json.loads(subprocess.check_output(command + ['config', '--format', 'json'], stderr=subprocess.PIPE))
            with self.subTest(files=files):
                self.assertEqual(validate(config, cpu_count, 12 * 1024 * MIB), expected_mib * MIB)

    def test_default_budget_includes_sibling_bots_and_reserve(self):
        self.assertEqual(validate(layout(), 8, 12 * 1024 * MIB), 9472 * MIB)

    def test_rejects_smoke_on_tournament_cpu(self):
        config = layout()
        config['services']['build-worker']['environment']['RUNNER_CPUSET_BUILD'] = '0'
        with self.assertRaisesRegex(ValueError, 'compiler/smoke'):
            validate(config, 8, 12 * 1024 * MIB)

    def test_rejects_overlapping_bot_and_control_cpus(self):
        for name, field, value in [('match-1', 'RUNNER_CPUSET_BLUE', '0'),
                                    ('match-0', 'RUNNER_CPUSET_BLUE', '6')]:
            config = layout()
            config['services'][name]['environment'][field] = value
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'overlaps'):
                validate(config, 8, 12 * 1024 * MIB)
        config = layout()
        config['services']['build-worker']['cpuset'] = '0-7'
        with self.assertRaisesRegex(ValueError, 'auxiliary'):
            validate(config, 8, 12 * 1024 * MIB)

    def test_rejects_small_host_and_missing_caps(self):
        for cpu_count, ram in [(4, 12 * 1024 * MIB), (8, 8 * 1024 * MIB)]:
            with self.subTest(cpu_count=cpu_count), self.assertRaises(ValueError):
                validate(layout(), cpu_count, ram)
        for field in ('mem_limit', 'cpus', 'pids_limit'):
            config = layout()
            del config['services']['match-0'][field]
            with self.subTest(field=field), self.assertRaises(ValueError):
                validate(config, 8, 12 * 1024 * MIB)

    def test_rejects_mixed_queues(self):
        config = copy.deepcopy(layout())
        config['services']['match-0']['command'] += ['--queue', 'match:scrimmage']
        with self.assertRaisesRegex(ValueError, 'exactly one'):
            validate(config, 8, 12 * 1024 * MIB)
