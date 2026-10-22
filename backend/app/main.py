"""ASGI entrypoint: `uvicorn app.main:app`. HTTP under /api/v1, WebSocket at /ws."""
from __future__ import annotations

import logging
import re
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.concurrency import run_in_threadpool

from app import contract, errors
from app.audit import audit_separately
from app.config import get_settings

log = logging.getLogger('ottv2')
API_PREFIX = '/api/v1'
_ADMIN_ID = re.compile(r'/api/v1/admin/(?P<kind>[a-z-]+)/(?P<id>[0-9a-f-]{36})')


def create_app() -> FastAPI:
    contract.check_version()
    settings = get_settings()
    from app.ws.hub import hub

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        await hub.start()
        try:
            yield
        finally:
            await hub.stop()

    # The reviewed contract (contracts/openapi.yaml) is the API description; FastAPI's own schema is disabled
    # so nobody consumes a second, code-derived OpenAPI by accident.
    app = FastAPI(title='OTTv2 Arena backend', openapi_url=None, docs_url=None, redoc_url=None, lifespan=lifespan)
    errors.install(app)

    @app.middleware('http')
    async def audit_rejected_admin_mutations(request: Request, call_next):
        response = await call_next(request)
        path = request.url.path
        if (response.status_code == 409 and request.method not in ('GET', 'HEAD')
                and path.startswith(API_PREFIX + '/admin/')):
            match = _ADMIN_ID.match(path)
            target_id = uuid.UUID(match['id']) if match else None
            route = request.scope.get('route')
            action = f'{getattr(route, "name", "admin")}.rejected'
            await run_in_threadpool(audit_separately, getattr(request.state, 'actor_id', None), action,
                                    match['kind'] if match else 'admin', target_id,
                                    {'error_code': getattr(request.state, 'error_code', None), 'path': path})
        return response

    if settings.origins:
        app.add_middleware(CORSMiddleware, allow_origins=settings.origins, allow_credentials=True,
                           allow_methods=['GET', 'POST', 'PUT', 'PATCH', 'DELETE'],
                           allow_headers=['Authorization', 'Content-Type', 'Idempotency-Key'],
                           expose_headers=['X-Request-ID', 'Retry-After'])

    from app.admin.router import router as admin_router
    from app.auth.router import router as auth_router
    from app.internal.router import router as internal_router
    from app.matches.router import router as matches_router
    from app.public.router import router as public_router
    from app.submissions.router import router as submissions_router
    from app.teams.router import router as teams_router
    from app.tournament.router import router as tournament_router
    from app.ws.router import router as ws_router

    for router in (public_router, auth_router, teams_router, submissions_router, matches_router, tournament_router,
                   admin_router, internal_router):
        app.include_router(router, prefix=API_PREFIX)
    app.include_router(ws_router)
    return app


app = create_app()
