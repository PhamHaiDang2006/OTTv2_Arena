import uuid

from alembic import command

from tests.helpers import bearer, make_user, token_for
from tests.test_migrations import config

EDIT = {'display_name': 'Cáo chiến thuật', 'bio': 'Chơi Hexagon cùng mình!',
        'avatar': 'fox', 'frame': 'laurel', 'color': 'jade'}


def test_public_profile_and_owner_only_edit(api):
    uid = make_user('private@example.test')
    auth = bearer(token_for(uid))
    path = f'/api/v1/profiles/{uid}'
    initial = api.get(path)
    assert initial.status_code == 200
    assert 'email' not in initial.text and 'private@example.test' not in initial.text
    assert initial.json()['stats']['played'] == 0
    assert api.get('/api/v1/profiles/me').status_code == 401
    assert api.put('/api/v1/profiles/me', json=EDIT).status_code == 401
    key = str(uuid.uuid4())
    updated = api.put('/api/v1/profiles/me', headers=auth, json=EDIT, idem=key)
    assert updated.status_code == 200
    assert api.put('/api/v1/profiles/me', headers=auth, json=EDIT, idem=key).json() == updated.json()
    assert api.get(path).json()['display_name'] == EDIT['display_name']
    other = make_user('other@example.test')
    api.put('/api/v1/profiles/me', headers=bearer(token_for(other)), json={**EDIT, 'display_name': 'Other'})
    assert api.get(path).json()['display_name'] == EDIT['display_name']
    for bad in ({'avatar': 'https://example.test/a.svg'}, {'display_name': '  '}, {'bio': 'x'*241},
                {'user_id': str(other)}, {'stats': {'wins': 999}}):
        assert api.put('/api/v1/profiles/me', headers=auth, json={**EDIT, **bad}).status_code == 422
    inactive = make_user('inactive@example.test', active=False)
    assert api.get(f'/api/v1/profiles/{inactive}').status_code == 404


def test_stats_survive_rematch_and_do_not_double_count(api):
    a, b = make_user('a@example.test'), make_user('b@example.test')
    ah, bh = bearer(token_for(a)), bearer(token_for(b))
    room = api.post('/api/v1/rooms', headers=ah, json={'map': 'circular'}).json()
    url = f'/api/v1/rooms/{room["id"]}'
    api.post('/api/v1/rooms/join', headers=bh, json={'code': room['code']})

    def command(headers, action, key=True):
        revision = api.get(url, headers=headers).json()['revision']
        return api.post(url+'/commands', headers=headers, json={'revision': revision, 'action': action}, idem=key)

    command(ah, 'ready')
    command(bh, 'ready')
    assert api.get(f'/api/v1/profiles/{a}').json()['stats']['played'] == 0
    command(bh, 'resign')
    command(ah, 'rematch')
    command(bh, 'rematch')
    # Seats switched; A is RED and resigns, so B wins round two.
    command(ah, 'resign')
    command(bh, 'leave')  # Closing a finished room must not count again.
    for uid in (a, b):
        stats = api.get(f'/api/v1/profiles/{uid}').json()['stats']
        assert (stats['played'], stats['wins'], stats['losses']) == (2, 1, 1)
        assert stats['by_map'][2] == {'map': 'circular', 'played': 2, 'wins': 1, 'losses': 1}
    fresh = api.post('/api/v1/rooms', headers=ah, json={'map': 'hexagon'}).json()
    api.post(f'/api/v1/rooms/{fresh["id"]}/commands', headers=ah, json={'revision': 0, 'action': 'leave'})
    assert api.get(f'/api/v1/profiles/{a}').json()['stats']['played'] == 2


def test_migration_backfills_existing_terminal_round(api):
    a, b = make_user('old-a@example.test'), make_user('old-b@example.test')
    ah, bh = bearer(token_for(a)), bearer(token_for(b))
    room = api.post('/api/v1/rooms', headers=ah, json={'map': 'hexagon'}).json()
    api.post('/api/v1/rooms/join', headers=bh, json={'code': room['code']})
    url = f'/api/v1/rooms/{room["id"]}'
    for who, action in ((ah, 'ready'), (bh, 'ready'), (bh, 'resign')):
        revision = api.get(url, headers=who).json()['revision']
        api.post(url+'/commands', headers=who, json={'revision': revision, 'action': action})
    command.downgrade(config(), '0003')
    command.upgrade(config(), 'head')
    stats = api.get(f'/api/v1/profiles/{a}').json()['stats']
    assert (stats['played'], stats['wins'], stats['losses']) == (1, 1, 0)
