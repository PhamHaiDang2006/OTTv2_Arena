"""Validate rendered runner Compose budgets against the Docker host, without printing secrets."""
import argparse
import json
import re
import subprocess

MIB = 1024 ** 2


def cpus(value):
    result = set()
    for part in str(value).split(','):
        if not re.fullmatch(r'\d+(?:-\d+)?', part):
            raise ValueError(f'Invalid CPU set: {value!r}')
        ends = [int(n) for n in part.split('-')]
        start, end = ends[0], ends[-1]
        if end < start or end > 4095:
            raise ValueError(f'Invalid CPU range: {part}')
        result.update(range(start, end + 1))
    return result


def memory(value):
    match = re.fullmatch(r'(\d+)([kmgt]?)b?', str(value).lower())
    if not match:
        raise ValueError('Missing or invalid memory limit')
    return int(match[1]) * 1024 ** ('kmgt'.index(match[2]) + 1 if match[2] else 0)


def validate(config, cpu_count, memory_bytes, reserve_mib=2048):
    services = config['services']
    auxiliary = cpus(services['registry'].get('cpuset', ''))
    official = set()
    used = set(auxiliary)
    budget = reserve_mib * MIB
    for name, service in services.items():
        command = service.get('command') or []
        if isinstance(command, str):
            command = command.split()
        worker = 'ottv2-runner-worker' in command
        if not worker and name != 'registry':
            continue
        control = cpus(service.get('cpuset', ''))
        if not control <= auxiliary:
            raise ValueError(f'{name}: worker/registry must run on auxiliary CPUs')
        quota = float(service.get('cpus', 0))
        cap = memory(service.get('mem_limit', ''))
        if not 0 < quota <= len(control) or cap <= 0:
            raise ValueError(f'{name}: missing or excessive CPU/RAM cap')
        if memory(service.get('memswap_limit', '')) != cap:
            raise ValueError(f'{name}: disable extra swap with memswap_limit=mem_limit')
        if int(service.get('pids_limit', 0)) <= 0:
            raise ValueError(f'{name}: finite pids_limit required')
        budget += cap
        if not worker:
            continue
        queues = [command[i + 1] for i, token in enumerate(command[:-1]) if token == '--queue']
        if len(queues) != 1 or queues[0] not in ('build', 'match:tournament', 'match:scrimmage'):
            raise ValueError(f'{name}: use exactly one build/tournament/scrimmage queue')
        env = service.get('environment', {})
        if queues[0] == 'build':
            build = cpus(env.get('RUNNER_CPUSET_BUILD', ''))
            if not build <= auxiliary:
                raise ValueError(f'{name}: compiler/smoke must stay on auxiliary CPUs')
            used |= build
            budget += 512 * MIB  # compiler and smoke run sequentially
            continue
        blue = cpus(env.get('RUNNER_CPUSET_BLUE', ''))
        red = cpus(env.get('RUNNER_CPUSET_RED', ''))
        if len(blue) != 1 or len(red) != 1 or blue & red:
            raise ValueError(f'{name}: each bot needs a different single CPU')
        pair = blue | red
        if queues[0] == 'match:tournament':
            if pair & (auxiliary | official):
                raise ValueError(f'{name}: tournament CPU overlaps another bot or auxiliary work')
            official |= pair
        elif not pair <= auxiliary:
            raise ValueError(f'{name}: scrimmage must stay on auxiliary CPUs')
        used |= pair
        budget += 1024 * MIB  # two sibling bot containers, not inside worker cgroup
    if not official:
        raise ValueError('No dedicated tournament worker found')
    if max(used) >= cpu_count:
        raise ValueError(f'CPU {max(used)} requested, Docker exposes only {cpu_count} CPUs')
    if budget > memory_bytes:
        raise ValueError(f'Need at least {budget / 1024**3:.2f} GiB including reserve; '
                         f'Docker exposes {memory_bytes / 1024**3:.2f} GiB')
    return budget


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', required=True)
    parser.add_argument('-f', '--compose', action='append', required=True)
    parser.add_argument('--reserve-mib', type=int, default=2048)
    args = parser.parse_args()
    if args.reserve_mib < 2048:
        parser.error('Keep at least 2048 MiB for Docker/OS and unbudgeted services')
    command = ['docker', 'compose', '--env-file', args.env_file]
    for path in args.compose:
        command += ['-f', path]
    try:
        # Keep interpolated environment (including credentials) in memory only.
        config = json.loads(subprocess.check_output(command + ['config', '--format', 'json'], stderr=subprocess.PIPE))
        host = json.loads(subprocess.check_output(['docker', 'info', '--format', '{{json .}}'], stderr=subprocess.PIPE))
        budget = validate(config, host['NCPU'], host['MemTotal'], args.reserve_mib)
    except subprocess.CalledProcessError:
        parser.exit(1, 'Cannot render Compose or read Docker host; check Docker and required environment settings.\n')
    except (ValueError, KeyError) as exc:
        parser.exit(1, f'Resource check failed: {exc}\n')
    print(f'Resource layout OK; budget including reserve: {budget / 1024**3:.2f} GiB. '
          'This does not isolate host daemons, disk I/O or physical CPU siblings.')


if __name__ == '__main__':
    main()
