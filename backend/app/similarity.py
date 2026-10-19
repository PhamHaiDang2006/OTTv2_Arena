"""Basic code similarity between official (frozen) submissions: normalized token k-grams with winnowing,
Jaccard over fingerprints. Only a screening aid for admins; it never changes results."""
from __future__ import annotations

import hashlib
import io
import re
import uuid
import zipfile
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from app.audit import audit
from app.db import session_scope
from app.models import CodeSimilarity, FrozenBot, Submission
from app.storage import get_storage
from app.timeutil import utcnow

K = 8
WINDOW = 4
SOURCE_SUFFIXES = ('.py', '.cpp', '.h', '.hpp', '.java', '.js')
KEYWORDS = set('''if else elif for while return def class import from in not and or try except finally with as
pass break continue lambda yield global nonlocal int long char bool void auto const static struct public private
protected new delete include using namespace template typename true false null none self this function var let
switch case default do throw catch'''.split())
TOKEN = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|[A-Za-z_]\w*|\d+(?:\.\d+)?|\S')
COMMENTS = re.compile(r'/\*.*?\*/|//[^\n]*|#[^\n]*', re.S)


def tokens(source: str) -> list[str]:
    result = []
    for tok in TOKEN.findall(COMMENTS.sub(' ', source)):
        if tok[0] in '"\'':
            result.append('S')
        elif tok[0].isdigit():
            result.append('N')
        elif tok[0].isalpha() or tok[0] == '_':
            result.append(tok if tok.lower() in KEYWORDS else 'V')
        else:
            result.append(tok)
    return result


def fingerprints(source: str) -> set[int]:
    toks = tokens(source)
    hashes = [int.from_bytes(hashlib.blake2b(' '.join(toks[i:i + K]).encode(), digest_size=8).digest(), 'big')
              for i in range(max(len(toks) - K + 1, 0))]
    if len(hashes) <= WINDOW:
        return set(hashes)
    return {min(hashes[i:i + WINDOW]) for i in range(len(hashes) - WINDOW + 1)}


def jaccard(a: set[int], b: set[int]) -> float:
    if not a and not b:
        return 0.0
    return len(a & b) / len(a | b)


def submission_text(row: Submission) -> str:
    data, _ = get_storage().read(row.source_key)
    parts = []
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        for entry in row.source_manifest:
            if entry['path'].endswith(SOURCE_SUFFIXES):
                parts.append(archive.read(entry['path']).decode('utf-8', errors='replace'))
    return '\n'.join(parts)


def compute_for_snapshot(snapshot_id: uuid.UUID) -> int:
    with session_scope() as db:
        ids = list(db.scalars(select(FrozenBot.submission_id).where(FrozenBot.snapshot_id == snapshot_id)))
        rows = list(db.scalars(select(Submission).where(Submission.id.in_(ids))))
    prints = {row.id: fingerprints(submission_text(row)) for row in rows}
    now = utcnow()
    with session_scope() as db:
        for left, right in combinations(sorted(prints, key=str), 2):
            a, b = (left, right) if str(left) < str(right) else (right, left)
            score = round(jaccard(prints[a], prints[b]), 4)
            db.execute(insert(CodeSimilarity).values(submission_a=a, submission_b=b, score=score, checked_at=now)
                       .on_conflict_do_update(index_elements=['submission_a', 'submission_b'],
                                              set_={'score': score, 'checked_at': now}))
        audit(db, None, 'similarity.computed', 'snapshot', snapshot_id, {'submissions': len(prints)})
    return len(prints)
