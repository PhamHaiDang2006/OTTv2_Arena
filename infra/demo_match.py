"""Create/reuse two demo players, upload real Python kits and request a real match via HTTP.

Run from repo root after start-local-play.ps1. No DB access, fake callback, or fake engine.
Demo credentials and operation keys stay in gitignored infra/.local-demo.json.
"""
import json
import secrets
import time
import uuid
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / 'infra/.local-demo.json'


def main():
    state = json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {
        'teams': [dict(strategy=s, email=f'demo-{s}@example.test', password=secrets.token_urlsafe(20),
                       name=f'Demo {s.title()}', upload_key=str(uuid.uuid4())) for s in ('random', 'greedy')],
        'match_key': str(uuid.uuid4()),
    }

    def save():
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')

    save()
    clients = []
    for team in state['teams']:
        client = httpx.Client(base_url='http://127.0.0.1:5173/api/v1', timeout=30,
                              headers={'Origin': 'http://127.0.0.1:5173'})
        clients.append(client)
        response = client.post('/auth/register', json={'email': team['email'], 'password': team['password'],
                                                       'team_name': team['name']}) if not team.get('team_id') else None
        if response is None or response.status_code == 409:
            response = client.post('/auth/login', json={'email': team['email'], 'password': team['password']})
        response.raise_for_status()
        auth = response.json()
        team['team_id'] = auth['user']['team_id']
        client.headers['Authorization'] = 'Bearer ' + auth['access_token']
        save()
        if not team.get('submission_id'):
            path = ROOT / f"starter-kits/dist/ottv2-python-{team['strategy']}-1.0.0.zip"
            with path.open('rb') as source:
                response = client.post('/submissions', data={'language': 'python'},
                                       files={'file': (path.name, source, 'application/zip')},
                                       headers={'Idempotency-Key': team['upload_key']})
            response.raise_for_status()
            team['submission_id'] = response.json()['id']
            save()
        print(f"{team['name']}: submission {team['submission_id']}", flush=True)

    deadline = time.monotonic() + 600
    previous = None
    while time.monotonic() < deadline:
        statuses = []
        for team, client in zip(state['teams'], clients):
            response = client.get(f"/submissions/{team['submission_id']}")
            response.raise_for_status()
            status = response.json()['status']
            if status == 'failed':
                log = client.get(f"/submissions/{team['submission_id']}/build-log").json()
                raise RuntimeError(f"{team['name']} build failed: {log}")
            statuses.append(status)
        if statuses != previous:
            print('Build: ' + ', '.join(statuses), flush=True)
            previous = statuses
        if all(s == 'ready' for s in statuses):
            break
        time.sleep(2)
    else:
        raise TimeoutError('Build still pending; inspect admin queue and worker logs, then rerun this script.')
    for team, client in zip(state['teams'], clients):
        response = client.put('/teams/me/active-bot', json={'scope': 'scrimmage', 'submission_id': team['submission_id']},
                              headers={'Idempotency-Key': str(uuid.uuid4())})
        response.raise_for_status()
    if not state.get('match_id'):
        response = clients[0].post('/scrimmages', json={'opponent_team_id': state['teams'][1]['team_id']},
                                   headers={'Idempotency-Key': state['match_key']})
        response.raise_for_status()
        state['match_id'] = response.json()['match_id']
        save()
    print(f"Admin: http://127.0.0.1:5174/admin/matches/{state['match_id']}", flush=True)
    previous = None
    for _ in range(300):
        response = clients[0].get(f"/matches/{state['match_id']}")
        response.raise_for_status()
        match = response.json()
        if match['status'] != previous:
            print('Match: ' + match['status'], flush=True)
            previous = match['status']
        if match['status'] in ('finished', 'blocked'):
            state['result'] = match
            save()
            print(json.dumps(match, ensure_ascii=False), flush=True)
            if match['status'] == 'blocked':
                raise RuntimeError('Match blocked; inspect worker logs before rerunning.')
            break
        time.sleep(2)
    else:
        raise TimeoutError('Match still pending; inspect admin queue.')
    for client in clients:
        client.post('/auth/logout')
        client.close()


if __name__ == '__main__':
    main()
