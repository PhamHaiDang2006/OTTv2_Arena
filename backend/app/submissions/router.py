"""Participant submission endpoints: upload ZIP, list, detail, build log, own source."""
from __future__ import annotations

import hashlib
import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.orm import Session
from starlette.datastructures import UploadFile

from app import idempotency, ratelimit
from app import serializers as ser
from app.config import get_settings
from app.db import get_db
from app.deps import Actor, OpInput, contract_input, require_member, require_team
from app.errors import ApiError, invalid
from app.models import Submission, Team
from app.queue import commit
from app.storage import StorageError, get_storage, submission_source_key, unavailable
from app.submissions import service
from app.submissions.archive import MAX_ZIP_BYTES, inspect
from app.teams.router import ensure_team_active

router = APIRouter()
MAX_REQUEST_BYTES = 2 * 1024 * 1024


async def upload_form(request: Request) -> tuple[bytes, str]:
    """Parse multipart {file, language} strictly: exactly those two fields, file read with a hard cap."""
    if not request.headers.get('content-type', '').startswith('multipart/form-data'):
        raise invalid('Chỉ nhận multipart/form-data')
    length = request.headers.get('content-length')
    if length is not None and length.isdigit() and int(length) > MAX_REQUEST_BYTES:
        raise ApiError(413, 'PAYLOAD_TOO_LARGE', 'Tệp ZIP vượt quá 1 MiB', {'reason': 'zip_too_large'})
    try:
        form = await request.form(max_files=1, max_fields=2, max_part_size=MAX_REQUEST_BYTES)
    except Exception as exc:  # noqa: BLE001 - malformed multipart from the client
        raise invalid('Dữ liệu multipart không hợp lệ') from exc
    keys = list(form.keys())
    if sorted(keys) != ['file', 'language'] or len(form.getlist('file')) != 1 or len(form.getlist('language')) != 1:
        raise invalid('Cần đúng hai trường file và language', fields=keys[:5])
    upload, language = form['file'], form['language']
    if not isinstance(upload, UploadFile) or not isinstance(language, str):
        raise invalid('Trường file phải là tệp, language phải là chuỗi')
    if language not in ('python', 'cpp', 'java', 'node'):
        raise invalid('Ngôn ngữ không hợp lệ', field='language')
    if language not in get_settings().languages:
        raise invalid('Ngôn ngữ này chưa được bật', field='language', enabled=get_settings().languages)
    data = await upload.read(MAX_ZIP_BYTES + 1)
    await form.close()
    return data, language


@router.post('/submissions', status_code=202)
def create_submission(request: Request, actor: Actor = Depends(require_member),
                      inp: OpInput = Depends(contract_input('createSubmission')),
                      form: tuple[bytes, str] = Depends(upload_form), db: Session = Depends(get_db)):
    data, language = form
    idem = idempotency.begin(db, request, actor.id, idempotency.hash_parts(data, language.encode()))
    if idem.replay:
        return idem.replay
    team_id = require_team(actor)
    team = db.get(Team, team_id, with_for_update=True)
    ensure_team_active(team)
    ratelimit.hit('submission', str(team.id), get_settings().submission_rate_per_hour, 3600)
    manifest = inspect(data, language)
    submission_id = uuid.uuid4()
    key = submission_source_key(str(submission_id))
    try:
        get_storage().put(key, data, 'application/zip')
    except StorageError as exc:
        raise unavailable(exc) from exc
    submission = Submission(id=submission_id, team_id=team.id, created_by=actor.id, language=language, source_key=key,
                            sha256=hashlib.sha256(data).hexdigest(), source_manifest=manifest, status='queued',
                            engine_version=get_settings().engine_version)
    db.add(submission)
    db.flush()
    service.create_build_job(db, submission)
    response = idem.record(202, {'id': str(submission.id), 'status': 'queued'})
    commit(db)
    return response


@router.get('/submissions')
def list_submissions(actor: Actor = Depends(require_member), inp: OpInput = Depends(contract_input('listSubmissions')),
                     db: Session = Depends(get_db)):
    query = select(Submission).where(Submission.team_id == actor.team_id)
    if inp.params['status']:
        query = query.where(Submission.status == inp.params['status'])
    query = query.order_by(Submission.submitted_at.desc(), Submission.id)
    return ser.page(db, query, inp.params['page'], inp.params['page_size'],
                    lambda rows: [ser.submission(r) for r in rows])


@router.get('/submissions/{id}')
def get_submission(actor: Actor = Depends(require_member), inp: OpInput = Depends(contract_input('getSubmission')),
                   db: Session = Depends(get_db)):
    return ser.submission(service.get_team_submission(db, inp.params['id'], actor.team_id))


@router.get('/submissions/{id}/build-log')
def get_build_log(actor: Actor = Depends(require_member), inp: OpInput = Depends(contract_input('getBuildLog')),
                  db: Session = Depends(get_db)):
    return service.build_log(service.get_team_submission(db, inp.params['id'], actor.team_id))


@router.get('/submissions/{id}/source')
def get_own_source(actor: Actor = Depends(require_member), inp: OpInput = Depends(contract_input('getOwnSource')),
                   db: Session = Depends(get_db)):
    return service.source_tree(service.get_team_submission(db, inp.params['id'], actor.team_id))


@router.get('/submissions/{id}/source-file')
def get_own_source_file(actor: Actor = Depends(require_member),
                        inp: OpInput = Depends(contract_input('getOwnSourceFile')), db: Session = Depends(get_db)):
    row = service.get_team_submission(db, inp.params['id'], actor.team_id)
    return service.source_file(row, inp.params['path'])
