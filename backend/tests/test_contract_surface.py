"""The implemented HTTP surface equals the contract: same (method, path) set as contracts/operations.json."""
from __future__ import annotations

from fastapi.routing import APIRoute, APIWebSocketRoute, iter_route_contexts

from app import contract


def test_routes_match_contract_operations(raw_client):
    contexts = list(iter_route_contexts(raw_client.app.routes))
    http = [(m, c.path) for c in contexts if isinstance(c.original_route, APIRoute) for m in c.original_route.methods]
    expected = {(op['method'].upper(), '/api/v1' + op['path']) for op in contract.operations()}
    assert len(http) == len(set(http))
    assert set(http) == expected
    assert [c.path for c in contexts if isinstance(c.original_route, APIWebSocketRoute)] == ['/ws']


def test_no_code_derived_openapi(api):
    assert api.raw.get('/openapi.json').status_code == 404
    assert api.raw.get('/docs').status_code == 404


def test_health_and_capabilities(api):
    assert api.get('/api/v1/health').json() == {'status': 'ok', 'contract_version': '1.2.0'}
    caps = api.get('/api/v1/capabilities').json()
    assert caps['languages'] == ['python', 'cpp']
    assert caps['ruleset_status'] == 'development'
    assert caps['tournament_enabled'] is True


def test_capabilities_reflects_development_flag(api):
    from app.config import get_settings
    get_settings().allow_development_tournaments = False
    assert api.get('/api/v1/capabilities').json()['tournament_enabled'] is False


def test_docs_serves_shared_rules(api):
    body = api.get('/api/v1/docs').json()
    assert 'dev-v1' in body['rules_markdown']
    assert 'OTTV2 1' in body['protocol_markdown']
    assert body['starter_kits'] == []


def test_unknown_route_uses_error_envelope(api):
    response = api.get('/api/v1/nope')
    assert response.status_code == 404
    assert response.json()['error']['code'] == 'NOT_FOUND'
    assert response.headers['X-Request-ID'] == response.json()['request_id']


def test_invalid_path_uuid_and_pagination(api):
    from tests.helpers import make_team
    team = make_team('doi-a')
    assert api.get('/api/v1/matches/not-a-uuid', headers=team.member).status_code == 422
    assert api.get('/api/v1/announcements?page=0').status_code == 422
    assert api.get('/api/v1/announcements?page_size=101').status_code == 422
    assert api.get('/api/v1/standings').status_code == 422
