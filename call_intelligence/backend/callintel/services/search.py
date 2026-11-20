"""Meaning-based search over transcript turns (Qwen3-Embedding-4B through the gateway).

Each turn is embedded with the turn before it, so short replies keep their context. Vectors live in the turns table;
the search loads an enterprise's vectors into memory once (refreshed when the count changes).
"""
import threading

import numpy as np
from sqlalchemy.orm import Session

from ..models import Call, Turn
from . import llm

_cache: dict[tuple, tuple[int, np.ndarray, list[int]]] = {}
_lock = threading.Lock()


def embed_call(db: Session, call: Call):
    turns = [t for t in call.turns if t.text.strip()]
    if not turns:
        return
    texts, prev = [], ""
    for t in turns:
        texts.append(f"{prev}\n{t.speaker}: {t.text}".strip())
        prev = f"{t.speaker}: {t.text}"
    for t, v in zip(turns, llm.embed(texts)):
        a = np.asarray(v, dtype=np.float32)
        a /= (np.linalg.norm(a) or 1)
        t.embedding = [round(float(x), 5) for x in a]


def _matrix(db: Session, ents: list[str]):
    key = tuple(sorted(ents))
    n = (db.query(Turn.id).join(Call).filter(Call.enterprise_id.in_(ents), Turn.embedding.isnot(None)).count())
    with _lock:
        hit = _cache.get(key)
        if hit and hit[0] == n:
            return hit[1], hit[2]
    rows = (db.query(Turn.id, Turn.embedding).join(Call)
            .filter(Call.enterprise_id.in_(ents), Turn.embedding.isnot(None)).all())
    ids = [r[0] for r in rows]
    mat = np.asarray([r[1] for r in rows], dtype=np.float32) if rows else np.zeros((0, 1), np.float32)
    with _lock:
        _cache[key] = (n, mat, ids)
    return mat, ids


def search(db: Session, ents: list[str], query: str, limit: int = 20, call_ids: set[str] | None = None) -> list[dict]:
    mat, ids = _matrix(db, ents)
    if not len(ids):
        return []
    q = np.asarray(llm.embed([query])[0], dtype=np.float32)
    q /= (np.linalg.norm(q) or 1)
    scores = mat @ q
    order = np.argsort(-scores)
    out, seen = [], set()
    for i in order[: limit * 8]:
        t = db.get(Turn, ids[int(i)])
        if not t or (call_ids is not None and t.call_id not in call_ids) or t.call_id in seen:
            continue
        seen.add(t.call_id)               # best moment per call
        out.append({"call_id": t.call_id, "turn": t.idx, "speaker": t.speaker, "text": t.text,
                    "score": round(float(scores[int(i)]), 3)})
        if len(out) >= limit:
            break
    return out
