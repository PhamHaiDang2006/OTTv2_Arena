"""Public tournament data: tournaments, rounds, standings, bracket."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app import serializers as ser
from app.db import get_db
from app.deps import OpInput, contract_input
from app.models import BracketSlot, Group, Round, Standing, Team, Tournament
from app.tournament.service import get_tournament

router = APIRouter()
SLOT_PLAY_ORDER = case({'quarterfinal': 1, 'semifinal': 2, 'third_place': 3, 'final': 4}, value=BracketSlot.round)


@router.get('/tournaments')
def list_tournaments(inp: OpInput = Depends(contract_input('listTournaments')), db: Session = Depends(get_db)):
    query = select(Tournament).order_by(Tournament.created_at.desc(), Tournament.id)
    return ser.page(db, query, inp.params['page'], inp.params['page_size'],
                    lambda rows: [ser.tournament(r) for r in rows])


@router.get('/tournaments/{id}')
def get_tournament_detail(inp: OpInput = Depends(contract_input('getTournament')), db: Session = Depends(get_db)):
    return ser.tournament(get_tournament(db, inp.params['id']))


def rounds_page(db: Session, tournament_id, page: int, page_size: int) -> dict:
    get_tournament(db, tournament_id)
    query = select(Round).where(Round.tournament_id == tournament_id).order_by(Round.created_at.desc(), Round.id)
    return ser.page(db, query, page, page_size, lambda rows: [ser.round_(db, r) for r in rows])


@router.get('/tournaments/{id}/rounds')
def list_rounds(inp: OpInput = Depends(contract_input('listRounds')), db: Session = Depends(get_db)):
    return rounds_page(db, inp.params['id'], inp.params['page'], inp.params['page_size'])


@router.get('/standings')
def get_standings(inp: OpInput = Depends(contract_input('getStandings')), db: Session = Depends(get_db)):
    get_tournament(db, inp.params['tournament_id'])
    query = (select(Standing).join(Group, Group.id == Standing.group_id)
             .where(Group.tournament_id == inp.params['tournament_id']).order_by(Group.label, Standing.rank))
    if inp.params['group_id']:
        query = query.where(Standing.group_id == inp.params['group_id'])

    def render(rows):
        rows = list(rows)
        teams = {t.id: t for t in db.scalars(select(Team).where(Team.id.in_([r.team_id for r in rows])))}
        return [ser.standing(r, teams[r.team_id]) for r in rows]
    return ser.page(db, query, inp.params['page'], inp.params['page_size'], render)


@router.get('/bracket')
def get_bracket(inp: OpInput = Depends(contract_input('getBracket')), db: Session = Depends(get_db)):
    get_tournament(db, inp.params['tournament_id'])
    query = (select(BracketSlot).where(BracketSlot.tournament_id == inp.params['tournament_id'])
             .order_by(SLOT_PLAY_ORDER, BracketSlot.slot_index))

    def render(rows):
        rows = list(rows)
        ids = [r.team_id for r in rows if r.team_id]
        teams = {t.id: t for t in db.scalars(select(Team).where(Team.id.in_(ids)))} if ids else {}
        return [ser.bracket_slot(r, teams.get(r.team_id)) for r in rows]
    return ser.page(db, query, inp.params['page'], inp.params['page_size'], render)
