"""Worker-only endpoints (/api/v1/internal/*). Caddy blocks this prefix publicly; the worker token is still
checked here. Callbacks are not idempotency-key operations: receipts + lease tokens provide deduplication."""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import OpInput, contract_input, require_worker, uuid_header
from app.errors import invalid
from app.internal import service
from app.models import WorkerStatus
from app.queue import commit
from app.timeutil import utcnow

router = APIRouter()
ACK = {'accepted': True}


@router.post('/internal/builds/{id}')
def build_callback(request: Request, _worker: None = Depends(require_worker),
                   inp: OpInput = Depends(contract_input('buildCallback')), db: Session = Depends(get_db)):
    lease = uuid_header(request, 'X-Worker-Lease')
    if inp.body['submission_id'] != str(inp.params['id']):
        raise invalid('ID trong URL khác submission_id trong payload', field='submission_id')
    service.handle_build(db, inp.params['id'], lease, inp.body)
    commit(db)
    return ACK


@router.post('/internal/games/{id}')
def game_callback(request: Request, _worker: None = Depends(require_worker),
                  inp: OpInput = Depends(contract_input('gameCallback')), db: Session = Depends(get_db)):
    lease = uuid_header(request, 'X-Worker-Lease')
    if inp.body['game_id'] != str(inp.params['id']):
        raise invalid('ID trong URL khác game_id trong payload', field='game_id')
    service.handle_game(db, inp.params['id'], lease, inp.body)
    commit(db)
    return ACK


@router.post('/internal/workers/heartbeat')
def worker_heartbeat(_worker: None = Depends(require_worker),
                     inp: OpInput = Depends(contract_input('workerHeartbeat')), db: Session = Depends(get_db)):
    body = inp.body
    job_id = uuid.UUID(body['job_id']) if body['job_id'] else None
    now = utcnow()  # server clock; the worker's sent_at is informational only
    db.execute(insert(WorkerStatus).values(id=body['worker_id'], kind=body['kind'], job_id=job_id, last_seen_at=now)
               .on_conflict_do_update(index_elements=[WorkerStatus.id],
                                      set_={'kind': body['kind'], 'job_id': job_id, 'last_seen_at': now}))
    db.commit()
    return ACK
