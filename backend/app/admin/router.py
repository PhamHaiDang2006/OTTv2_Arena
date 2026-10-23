"""Admin endpoints (/api/v1/admin/*). Every mutation is audited; rejected ones (409) are audited by middleware.
Function names equal contract operationIds (the rejection audit uses them as action names)."""
from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app import idempotency
from app import serializers as ser
from app.admin import teams as team_admin
from app.audit import audit, audit_separately
from app.db import get_db
from app.deps import Actor, OpInput, contract_input, require_admin
from app.errors import conflict, not_found
from app.matches import admission
from app.matches import service as match_service
from app.models import (
    QUEUES,
    Announcement,
    AuditLog,
    CodeSimilarity,
    Game,
    Match,
    QueueControl,
    RoundSnapshot,
    Submission,
    Team,
    Tournament,
    WorkerJob,
    WorkerStatus,
)
from app.queue import add_event, commit, deliver, drain
from app.storage import STDERR_FILES, StorageError, get_storage, unavailable
from app.submissions import service as submission_service
from app.timeutil import parse_iso, utcnow
from app.tournament import service as tournament
from app.tournament.router import rounds_page

router = APIRouter()
log = logging.getLogger('ottv2.admin')
LOG_LIMIT = 1024 * 1024


def _idem(db: Session, request: Request, actor: Actor, body) -> idempotency.Idempotency:
    return idempotency.begin(db, request, actor.id, idempotency.hash_json(body))


def _done(db: Session, idem: idempotency.Idempotency, status: int, body):
    response = idem.record(status, body)
    commit(db)
    return response


# --- teams ----------------------------------------------------------------------------------------------------

@router.get('/admin/teams')
def adminListTeams(actor: Actor = Depends(require_admin), inp: OpInput = Depends(contract_input('adminListTeams')),
                   db: Session = Depends(get_db)):
    query = select(Team).order_by(Team.created_at.desc(), Team.id)
    return ser.page(db, query, inp.params['page'], inp.params['page_size'], lambda rows: [ser.team(db, t) for t in rows])


@router.post('/admin/teams', status_code=201)
def adminCreateTeam(request: Request, actor: Actor = Depends(require_admin),
                    inp: OpInput = Depends(contract_input('adminCreateTeam')), db: Session = Depends(get_db)):
    idem = _idem(db, request, actor, inp.body)
    if idem.replay:
        return idem.replay
    b = inp.body
    team = team_admin.create_team(db, actor.id, team_admin.TeamSpec(b['name'], b['slug'], b['captain_email'], b['seed']))
    return _done(db, idem, 201, ser.team(db, team))


@router.patch('/admin/teams/{id}')
def adminUpdateTeam(request: Request, actor: Actor = Depends(require_admin),
                    inp: OpInput = Depends(contract_input('adminUpdateTeam')), db: Session = Depends(get_db)):
    idem = _idem(db, request, actor, inp.body)
    if idem.replay:
        return idem.replay
    team = db.get(Team, inp.params['id'], with_for_update=True)
    if team is None:
        raise not_found('Không tìm thấy đội')
    team_admin.update_team(db, actor.id, team, inp.body)
    return _done(db, idem, 200, ser.team(db, team))


@router.post('/admin/teams/import', status_code=201)
def adminImportTeams(request: Request, actor: Actor = Depends(require_admin),
                     inp: OpInput = Depends(contract_input('adminImportTeams')), db: Session = Depends(get_db)):
    idem = _idem(db, request, actor, inp.body)
    if idem.replay:
        return idem.replay
    specs, errors = team_admin.parse_import(db, inp.body['csv'])
    created = []
    if not errors:
        created = [team_admin.create_team(db, actor.id, spec, 'team.import') for spec in specs]
    audit(db, actor.id, 'team.import_batch', 'team', None, {'created': len(created), 'errors': errors[:50]})
    return _done(db, idem, 201, {'created': [ser.team_public(t) for t in created], 'errors': errors})


# --- submissions and source -----------------------------------------------------------------------------------

def _submission(db: Session, submission_id: uuid.UUID) -> Submission:
    row = db.get(Submission, submission_id)
    if row is None:
        raise not_found('Không tìm thấy bản nộp')
    return row


@router.get('/admin/submissions')
def adminListSubmissions(actor: Actor = Depends(require_admin),
                         inp: OpInput = Depends(contract_input('adminListSubmissions')), db: Session = Depends(get_db)):
    query = select(Submission)
    for name, column in (('team_id', Submission.team_id), ('language', Submission.language),
                         ('status', Submission.status)):
        if inp.params[name]:
            query = query.where(column == inp.params[name])
    query = query.order_by(Submission.submitted_at.desc(), Submission.id)
    return ser.page(db, query, inp.params['page'], inp.params['page_size'], lambda rows: [ser.submission(r) for r in rows])


@router.get('/admin/submissions/{id}')
def adminGetSubmission(actor: Actor = Depends(require_admin),
                       inp: OpInput = Depends(contract_input('adminGetSubmission')), db: Session = Depends(get_db)):
    return ser.submission(_submission(db, inp.params['id']))


@router.get('/admin/submissions/{id}/source')
def adminGetSource(actor: Actor = Depends(require_admin), inp: OpInput = Depends(contract_input('adminGetSource')),
                   db: Session = Depends(get_db)):
    return submission_service.source_tree(_submission(db, inp.params['id']))


@router.get('/admin/submissions/{id}/source-file')
def adminGetSourceFile(actor: Actor = Depends(require_admin),
                       inp: OpInput = Depends(contract_input('adminGetSourceFile')), db: Session = Depends(get_db)):
    return submission_service.source_file(_submission(db, inp.params['id']), inp.params['path'])


@router.get('/admin/submissions/{id}/build-log')
def adminBuildLog(actor: Actor = Depends(require_admin), inp: OpInput = Depends(contract_input('adminBuildLog')),
                  db: Session = Depends(get_db)):
    return submission_service.build_log(_submission(db, inp.params['id']))


# --- tournaments, draw, rounds --------------------------------------------------------------------------------

@router.get('/admin/tournaments')
def adminListTournaments(actor: Actor = Depends(require_admin),
                         inp: OpInput = Depends(contract_input('adminListTournaments')), db: Session = Depends(get_db)):
    query = select(Tournament).order_by(Tournament.created_at.desc(), Tournament.id)
    return ser.page(db, query, inp.params['page'], inp.params['page_size'], lambda rows: [ser.tournament(r) for r in rows])


@router.post('/admin/tournaments', status_code=201)
def adminCreateTournament(request: Request, actor: Actor = Depends(require_admin),
                          inp: OpInput = Depends(contract_input('adminCreateTournament')),
                          db: Session = Depends(get_db)):
    idem = _idem(db, request, actor, inp.body)
    if idem.replay:
        return idem.replay
    row = tournament.create_tournament(db, actor.id, inp.body)
    return _done(db, idem, 201, ser.tournament(row))


@router.get('/admin/tournaments/{id}/draw')
def adminGetDraw(actor: Actor = Depends(require_admin), inp: OpInput = Depends(contract_input('adminGetDraw')),
                 db: Session = Depends(get_db)):
    return tournament.draw_body(db, tournament.get_tournament(db, inp.params['id']))


@router.post('/admin/tournaments/{id}/draw')
def adminDraw(request: Request, actor: Actor = Depends(require_admin),
              inp: OpInput = Depends(contract_input('adminDraw')), db: Session = Depends(get_db)):
    idem = _idem(db, request, actor, inp.body)
    if idem.replay:
        return idem.replay
    row = tournament.get_tournament(db, inp.params['id'], lock=True)
    return _done(db, idem, 200, tournament.draw(db, actor.id, row, inp.body['reason']))


@router.post('/admin/tournaments/{id}/draw/lock')
def adminLockDraw(request: Request, actor: Actor = Depends(require_admin),
                  inp: OpInput = Depends(contract_input('adminLockDraw')), db: Session = Depends(get_db)):
    idem = _idem(db, request, actor, inp.body)
    if idem.replay:
        return idem.replay
    row = tournament.get_tournament(db, inp.params['id'], lock=True)
    return _done(db, idem, 200, tournament.lock_draw(db, actor.id, row, inp.body['reason']))


def _freeze_at(value):
    return parse_iso(value) if value else None


@router.post('/admin/tournaments/{id}/rounds', status_code=201)
def adminCreateRound(request: Request, actor: Actor = Depends(require_admin),
                     inp: OpInput = Depends(contract_input('adminCreateRound')), db: Session = Depends(get_db)):
    idem = _idem(db, request, actor, inp.body)
    if idem.replay:
        return idem.replay
    row = tournament.get_tournament(db, inp.params['id'], lock=True)
    created = tournament.create_round(db, actor.id, row, inp.body['stage'], _freeze_at(inp.body['freeze_at']))
    return _done(db, idem, 201, ser.round_(db, created))


@router.get('/admin/tournaments/{id}/rounds')
def adminListRounds(actor: Actor = Depends(require_admin), inp: OpInput = Depends(contract_input('adminListRounds')),
                    db: Session = Depends(get_db)):
    return rounds_page(db, inp.params['id'], inp.params['page'], inp.params['page_size'])


@router.patch('/admin/rounds/{id}')
def adminUpdateRound(request: Request, actor: Actor = Depends(require_admin),
                     inp: OpInput = Depends(contract_input('adminUpdateRound')), db: Session = Depends(get_db)):
    idem = _idem(db, request, actor, inp.body)
    if idem.replay:
        return idem.replay
    row = tournament.lock_round(db, inp.params['id'])
    tournament.update_round(db, actor.id, row, _freeze_at(inp.body['freeze_at']), inp.body['reason'])
    return _done(db, idem, 200, ser.round_(db, row))


@router.post('/admin/rounds/{id}/freeze')
def adminFreezeRound(request: Request, actor: Actor = Depends(require_admin),
                     inp: OpInput = Depends(contract_input('adminFreezeRound')), db: Session = Depends(get_db)):
    idem = _idem(db, request, actor, inp.body)
    if idem.replay:
        return idem.replay
    row = tournament.lock_round(db, inp.params['id'])
    snapshot = tournament.freeze_round(db, actor.id, row, inp.body['reason'])
    return _done(db, idem, 200, tournament.snapshot_body(db, snapshot))


@router.get('/admin/rounds/{id}/snapshot')
def adminGetSnapshot(actor: Actor = Depends(require_admin), inp: OpInput = Depends(contract_input('adminGetSnapshot')),
                     db: Session = Depends(get_db)):
    tournament.get_round(db, inp.params['id'])
    snapshot = db.scalar(select(RoundSnapshot).where(RoundSnapshot.round_id == inp.params['id']))
    if snapshot is None:
        raise not_found('Vòng chưa được đóng băng')
    return tournament.snapshot_body(db, snapshot)


@router.post('/admin/rounds/{id}/run', status_code=202)
def adminRunRound(request: Request, actor: Actor = Depends(require_admin),
                  inp: OpInput = Depends(contract_input('adminRunRound')), db: Session = Depends(get_db)):
    idem = _idem(db, request, actor, inp.body)
    if idem.replay:
        return idem.replay
    row = tournament.lock_round(db, inp.params['id'])
    created = tournament.run_round(db, actor.id, row, inp.body['reason'])
    return _done(db, idem, 202, {'round_id': str(row.id), 'status': 'running', 'match_ids': [str(m.id) for m in created]})


# --- matches and games ----------------------------------------------------------------------------------------

@router.get('/admin/matches')
def adminListMatches(actor: Actor = Depends(require_admin), inp: OpInput = Depends(contract_input('adminListMatches')),
                     db: Session = Depends(get_db)):
    query = select(Match)
    if inp.params['round_id']:
        query = query.where(Match.round_id == inp.params['round_id'])
    if inp.params['status']:
        query = query.where(Match.status == inp.params['status'])
    query = query.order_by(Match.created_at.desc(), Match.id)
    return ser.page(db, query, inp.params['page'], inp.params['page_size'], lambda rows: ser.matches(db, list(rows)))


@router.get('/admin/games/{id}/logs')
def adminGameLogs(actor: Actor = Depends(require_admin), inp: OpInput = Depends(contract_input('adminGameLogs')),
                  db: Session = Depends(get_db)):
    game = db.get(Game, inp.params['id'])
    if game is None:
        raise not_found('Không tìm thấy ván')
    body = {'game_id': str(game.id), 'BLUE': '', 'RED': '', 'blue_truncated': False, 'red_truncated': False}
    if game.log_key:
        for side, filename in STDERR_FILES.items():
            try:
                data, total = get_storage().read(game.log_key + filename, LOG_LIMIT)
            except FileNotFoundError:
                continue
            except StorageError as exc:
                raise unavailable(exc) from exc
            body[side] = data.decode('utf-8', errors='replace')
            body[f'{side.lower()}_truncated'] = total > LOG_LIMIT
    return body


@router.post('/admin/games/{id}/rerun', status_code=202)
def adminRerunGame(request: Request, actor: Actor = Depends(require_admin),
                   inp: OpInput = Depends(contract_input('adminRerunGame')), db: Session = Depends(get_db)):
    idem = _idem(db, request, actor, inp.body)
    if idem.replay:
        return idem.replay
    game, new = tournament.rerun_game(db, actor.id, inp.params['id'], inp.body['reason'])
    return _done(db, idem, 202, {'game_id': str(new.id), 'previous_game_id': str(game.id), 'attempt': new.attempt,
                                 'status': 'queued'})


@router.post('/admin/matches/{id}/override')
def adminOverrideMatch(request: Request, actor: Actor = Depends(require_admin),
                       inp: OpInput = Depends(contract_input('adminOverrideMatch')), db: Session = Depends(get_db)):
    idem = _idem(db, request, actor, inp.body)
    if idem.replay:
        return idem.replay
    match = match_service.get_match(db, inp.params['id'], lock=True)
    tournament.override_match(db, actor.id, match, inp.body)
    return _done(db, idem, 200, ser.match(db, match))


# --- queue and workers ----------------------------------------------------------------------------------------

def queue_body(db: Session) -> dict:
    paused = {q.name: q.paused for q in db.scalars(select(QueueControl))}
    since = utcnow() - timedelta(hours=24)
    queues = []
    def count(name: str, *where) -> int:
        return db.scalar(select(func.count()).select_from(WorkerJob).where(WorkerJob.queue == name, *where)) or 0
    for name in sorted(QUEUES):  # behavior.md: queue listed by name
        queues.append({'name': name, 'paused': paused.get(name, False),
                       'queued': count(name, WorkerJob.status == 'queued'),
                       'running': count(name, WorkerJob.status == 'running'),
                       'failed': count(name, WorkerJob.outcome == 'infra_error', WorkerJob.finished_at >= since)})
    workers = db.scalars(select(WorkerStatus).order_by(WorkerStatus.id))
    return {'queues': queues, 'workers': [ser.worker(w) for w in workers],
            'scrimmage_admission': admission.admission(db)}


@router.get('/admin/queue')
def adminQueue(actor: Actor = Depends(require_admin), db: Session = Depends(get_db)):
    return queue_body(db)


@router.put('/admin/queue')
def adminControlQueue(request: Request, actor: Actor = Depends(require_admin),
                      inp: OpInput = Depends(contract_input('adminControlQueue')), db: Session = Depends(get_db)):
    idem = _idem(db, request, actor, inp.body)
    if idem.replay:
        return idem.replay
    name, paused = inp.body['name'], inp.body['paused']
    control = db.get(QueueControl, name, with_for_update=True)
    before = control.paused if control is not None else False
    if control is None:
        control = QueueControl(name=name, paused=paused)
        db.add(control)
    control.paused, control.updated_at = paused, utcnow()
    db.flush()
    audit(db, actor.id, 'queue.control', 'queue', None,
          {'name': name, 'reason': inp.body['reason'], 'before': {'paused': before}, 'after': {'paused': paused}})
    # The pause is committed before RQ is touched; draining is repeatable and also re-run by the scheduler.
    response = _done(db, idem, 200, queue_body(db))
    try:
        if paused:
            drained = drain(name)
            audit_separately(actor.id, 'queue.drain', 'queue', None, {'name': name, 'removed_jobs': drained})
        else:
            deliver()
    except Exception as exc:  # noqa: BLE001 - the scheduler finishes draining / delivery
        log.warning('Queue %s %s incomplete: %s', name, 'drain' if paused else 'resume delivery', exc)
        audit_separately(actor.id, 'queue.drain_incomplete' if paused else 'queue.resume_incomplete', 'queue', None,
                         {'name': name, 'error': str(exc)[:300]})
    return response


# --- similarity, audit, announcements -------------------------------------------------------------------------

@router.get('/admin/similarity')
def adminSimilarity(actor: Actor = Depends(require_admin), inp: OpInput = Depends(contract_input('adminSimilarity')),
                    db: Session = Depends(get_db)):
    query = select(CodeSimilarity).order_by(CodeSimilarity.checked_at.desc(), CodeSimilarity.score.desc(),
                                            CodeSimilarity.submission_a, CodeSimilarity.submission_b)
    return ser.page(db, query, inp.params['page'], inp.params['page_size'], lambda rows: [ser.similarity(r) for r in rows])


@router.get('/admin/audit-log')
def adminAuditLog(actor: Actor = Depends(require_admin), inp: OpInput = Depends(contract_input('adminAuditLog')),
                  db: Session = Depends(get_db)):
    query = select(AuditLog)
    if inp.params['actor_user_id']:
        query = query.where(AuditLog.actor_user_id == inp.params['actor_user_id'])
    if inp.params['action']:
        query = query.where(AuditLog.action == inp.params['action'])
    query = query.order_by(AuditLog.created_at.desc(), AuditLog.id)
    return ser.page(db, query, inp.params['page'], inp.params['page_size'], lambda rows: [ser.audit(r) for r in rows])


@router.get('/admin/announcements')
def adminAnnouncements(actor: Actor = Depends(require_admin),
                       inp: OpInput = Depends(contract_input('adminAnnouncements')), db: Session = Depends(get_db)):
    query = select(Announcement).order_by(Announcement.created_at.desc(), Announcement.id)
    return ser.page(db, query, inp.params['page'], inp.params['page_size'], lambda rows: [ser.announcement(r) for r in rows])


@router.post('/admin/announcements', status_code=201)
def adminCreateAnnouncement(request: Request, actor: Actor = Depends(require_admin),
                            inp: OpInput = Depends(contract_input('adminCreateAnnouncement')),
                            db: Session = Depends(get_db)):
    idem = _idem(db, request, actor, inp.body)
    if idem.replay:
        return idem.replay
    row = Announcement(title=inp.body['title'], body=inp.body['body'])
    db.add(row)
    db.flush()
    audit(db, actor.id, 'announcement.create', 'announcement', row.id, {'title': row.title})
    return _done(db, idem, 201, ser.announcement(row))


def _announcement(db: Session, announcement_id: uuid.UUID) -> Announcement:
    row = db.get(Announcement, announcement_id, with_for_update=True)
    if row is None:
        raise not_found('Không tìm thấy thông báo')
    return row


@router.patch('/admin/announcements/{id}')
def adminUpdateAnnouncement(request: Request, actor: Actor = Depends(require_admin),
                            inp: OpInput = Depends(contract_input('adminUpdateAnnouncement')),
                            db: Session = Depends(get_db)):
    idem = _idem(db, request, actor, inp.body)
    if idem.replay:
        return idem.replay
    row = _announcement(db, inp.params['id'])
    if row.published_at is not None:
        raise conflict(message='Chỉ sửa được thông báo nháp', reason='published')
    before = {'title': row.title, 'body': row.body}
    row.title, row.body, row.updated_at = inp.body['title'], inp.body['body'], utcnow()
    audit(db, actor.id, 'announcement.update', 'announcement', row.id, {'before': before, 'after': inp.body})
    return _done(db, idem, 200, ser.announcement(row))


@router.post('/admin/announcements/{id}/publish')
def adminPublishAnnouncement(request: Request, actor: Actor = Depends(require_admin),
                             inp: OpInput = Depends(contract_input('adminPublishAnnouncement')),
                             db: Session = Depends(get_db)):
    idem = _idem(db, request, actor, inp.body)
    if idem.replay:
        return idem.replay
    row = _announcement(db, inp.params['id'])
    if row.published_at is None:  # publishing twice is a no-op: one event only
        row.published_at = utcnow()
        audit(db, actor.id, 'announcement.publish', 'announcement', row.id, {'reason': inp.body['reason']})
        add_event(db, 'announcement.published', 'public', {'announcement_id': str(row.id)})
    return _done(db, idem, 200, ser.announcement(row))
