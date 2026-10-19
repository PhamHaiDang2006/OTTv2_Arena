"""Submission reads shared by participant and admin endpoints, plus build job creation."""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.orm import Session

from app import contract
from app.errors import invalid, not_found
from app.models import Submission, WorkerJob
from app.queue import add_job
from app.serializers import s
from app.storage import StorageError, get_storage, unavailable
from app.submissions.archive import read_file
from app.timeutil import iso

BUILD_LOG_LIMIT = 1024 * 1024
SOURCE_FILE_LIMIT = 1024 * 1024


def create_build_job(db: Session, submission: Submission) -> WorkerJob:
    job_id = uuid.uuid4()
    payload = {'schema_version': contract.SCHEMA_VERSION, 'job_id': str(job_id), 'submission_id': str(submission.id),
               'language': submission.language, 'source_key': submission.source_key,
               'source_sha256': submission.sha256, 'engine_version': submission.engine_version}
    problems = contract.errors('BuildJob', payload)
    if problems:
        raise RuntimeError(f'BuildJob violates contract: {problems}')
    return add_job(db, WorkerJob(id=job_id, kind='build', queue='build', submission_id=submission.id,
                                 payload=payload))


def build_log(row: Submission) -> dict[str, Any]:
    text, truncated = '', False
    if row.build_log_key:
        try:
            data, total = get_storage().read(row.build_log_key, BUILD_LOG_LIMIT)
        except FileNotFoundError:
            data, total = b'', 0
        except StorageError as exc:
            raise unavailable(exc) from exc
        text, truncated = data.decode('utf-8', errors='replace'), total > BUILD_LOG_LIMIT
    return {'submission_id': s(row.id), 'status': row.status, 'text': text, 'truncated': truncated,
            'updated_at': iso(row.updated_at)}


def source_tree(row: Submission) -> dict[str, Any]:
    return {'submission_id': s(row.id), 'files': row.source_manifest}


def source_file(row: Submission, path: str) -> dict[str, Any]:
    if not any(entry['path'] == path for entry in row.source_manifest):
        raise not_found('Không có tệp này trong bản nộp')
    try:
        data, _ = get_storage().read(row.source_key)
    except FileNotFoundError as exc:
        raise not_found('Không tìm thấy mã nguồn') from exc
    except StorageError as exc:
        raise unavailable(exc) from exc
    try:
        content, truncated = read_file(data, path, SOURCE_FILE_LIMIT)
    except KeyError as exc:
        raise invalid('Tệp không có trong ZIP', path=path) from exc
    return {'submission_id': s(row.id), 'path': path, 'content': content, 'truncated': truncated}


def get_team_submission(db: Session, submission_id: uuid.UUID, team_id: uuid.UUID | None) -> Submission:
    row = db.get(Submission, submission_id)
    if row is None or team_id is None or row.team_id != team_id:
        raise not_found('Không tìm thấy bản nộp')
    return row
