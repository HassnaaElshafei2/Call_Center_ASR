"""Importers for the Call_Center_Data repository (private; real calls never leave it except into this app).

    python -m callintel.manage import-data /path/to/Call_Center_Data [--keep-dates] [--no-analysis]

  callcenter_data/real/{adib,btech}       real calls: transcripts/<call>.json (timed, with roles and metadata) + calls/<call>.wav|mp3
  callcenter_data/synthetic/elevenlabs    Mohammed's ElevenLabs calls: turns.jsonl + clips, calls/<call>_phone.wav, scripts/<call>.txt
  callcenter_data/synthetic/older_tts     Mohammed's older TTS calls: turns.jsonl + clips (no full recording: the clips are joined)
  elevenlabs_hs_phone_v2                  phone-quality audio of the 76 demo calls, with exact turn timings (calls.jsonl)

Real calls are source="real"; Mohammed's are source="synthetic" (the 76 demo calls stay "seed"), so dashboards can
show real calls only. By default dates are moved into the last four weeks, keeping each call's time of day, so the
default 30-day views include them; --keep-dates keeps the original recording dates.
"""
from __future__ import annotations

import json
import logging
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import soundfile as sf
from sqlalchemy.orm import Session

from .models import Agent, Call, Turn
from .seed import parse_script, _person
from .services import identity, jobs, storage
from .services.metrics import measure

log = logging.getLogger("callintel.import")
CAIRO = ZoneInfo("Africa/Cairo")
ROLE = {"agent": "agent", "customer": "customer", "ivr": "ivr"}


def _agent(db: Session, ent: str, name: str) -> Agent | None:
    name = (name or "").strip()
    if not name:
        return None
    a = db.query(Agent).filter_by(enterprise_id=ent, name=name).first()
    if not a:
        n = db.query(Agent).filter_by(enterprise_id=ent).count()
        a = Agent(enterprise_id=ent, name=name, code=f"IMP-{n + 1:03d}")
        db.add(a)
        db.flush()
    return a


def _store(call: Call, src: Path):
    dest = storage.path_for(call.enterprise_id, call.id, src.name)
    dest.write_bytes(src.read_bytes())
    call.audio_path = storage.relative(dest)


def _recent(original: datetime | None, rng: random.Random, days: int = 27) -> datetime:
    """A date in the last `days` days with the original Cairo time of day (or a working hour)."""
    local = original.astimezone(CAIRO) if original else None
    hour, minute = (local.hour, local.minute) if local else (rng.randint(9, 20), rng.randint(0, 59))
    now = datetime.now(CAIRO)
    t = (now - timedelta(days=rng.randint(0, days))).replace(hour=hour, minute=minute, second=0, microsecond=0)
    if t > now:                                          # today, but later than now: use the day before
        t -= timedelta(days=1)
    return t.astimezone(timezone.utc)


def _original_time(name: str, audio_source: str = "") -> datetime | None:
    m = re.search(r"(20\d{2})(\d{2})(\d{2})T(\d{2})(\d{2})(\d{2})", audio_source)          # B.TECH: 20260801T153620.400Z (UTC)
    if m:
        return datetime(*map(int, m.groups()), tzinfo=timezone.utc)
    m = re.match(r"(20\d{2})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", name)                   # ADIB: 20240811205505… (Cairo)
    if m:
        return datetime(*map(int, m.groups()), tzinfo=CAIRO).astimezone(timezone.utc)
    return None


def _exists(db: Session, ent: str, ref: str) -> bool:
    return db.query(Call.id).filter_by(enterprise_id=ent, external_ref=ref).first() is not None


def _finish(db: Session, call: Call, analyze: bool):
    cust = identity.from_recording_name(db, call)
    call.customer_id = cust.id if cust else None
    call.metrics = measure(call.turns)
    if analyze:
        jobs.enqueue(db, "analyze_call", {"call_id": call.id}, max_attempts=3)


# --------------------------------------------------------------------------------------------- real calls
def import_real(db: Session, folder: Path, enterprise: str, keep_dates: bool = False, analyze: bool = True) -> list[str]:
    """One call per transcripts/<name>.json: {"recording": {"audio_source", "metadata": {agent_name, topic, …},
    "segments": [{start, end, role, text}]}}; the recording is calls/<name>.wav|mp3."""
    rng = random.Random(f"real-{enterprise}")
    created = []
    for tf in sorted((folder / "transcripts").glob("*.json")):
        name = tf.stem
        if _exists(db, enterprise, name):
            continue
        rec = json.loads(tf.read_text(encoding="utf-8"))["recording"]
        meta, segs = rec.get("metadata", {}), rec.get("segments", [])
        original = _original_time(name, rec.get("audio_source", ""))
        started = original if keep_dates and original else _recent(original, rng)
        agent = _agent(db, enterprise, meta.get("agent_name", ""))
        call = Call(enterprise_id=enterprise, external_ref=name, source="real", status="analyzing", started_at=started,
                    agent_id=agent.id if agent else None, queue=(meta.get("topic") or "")[:80])
        for i, s in enumerate(x for x in segs if (x.get("text") or "").strip()):
            call.turns.append(Turn(idx=i, speaker=ROLE.get(s.get("role"), "unknown"), start=round(float(s["start"]), 2),
                                   end=round(float(s["end"]), 2), text=s["text"].strip()))
        audio = next(iter(sorted((folder / "calls").glob(name + ".*"))), None)
        call.duration_s = round(sf.info(str(audio)).duration, 1) if audio else (call.turns[-1].end if call.turns else 0)
        db.add(call)
        db.flush()
        if audio:
            _store(call, audio)
        _finish(db, call, analyze)
        created.append(call.id)
        log.info("real %s %s: %d turns, %.0f s", enterprise, name, len(call.turns), call.duration_s)
    db.commit()
    return created


# --------------------------------------------------------------------------------------------- Mohammed's synthetic calls
def _rows_by_call(path: Path) -> dict[str, list[dict]]:
    by: dict[str, list[dict]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            by.setdefault(r["call"], []).append(r)
    return by


def _enterprise_of(text: str) -> str:
    return "btech" if "بي تك" in text or "B.TECH" in text.upper() else "adib"


def import_elevenlabs(db: Session, folder: Path, analyze: bool = True) -> list[str]:
    """Mohammed's ElevenLabs calls: turn clips laid out in order, the gaps sized so they add up to the full call."""
    rng = random.Random("synthetic-el")
    created = []
    for cid, rows in sorted(_rows_by_call(folder / "turns.jsonl").items()):
        ent = _enterprise_of(" ".join(r["text"] for r in rows))
        ref = f"synthetic:{cid}"
        if _exists(db, ent, ref):
            continue
        script = folder / "scripts" / f"{cid}.txt"
        head = parse_script(script.read_text(encoding="utf-8"))["head"] if script.is_file() else {}
        audio = next((p for p in (folder / "calls" / f"{cid}_phone.wav", folder / "calls" / f"{cid}.wav") if p.is_file()), None)
        durs = [sf.info(str(folder / "turns" / r["file"])).duration if (folder / "turns" / r["file"]).is_file() else 2.0 for r in rows]
        total = sf.info(str(audio)).duration if audio else sum(durs) + .3 * len(rows)
        gap = max(0.0, (total - sum(durs)) / max(1, len(rows)))
        agent = _agent(db, ent, _person(head.get("agent", "")))
        call = Call(enterprise_id=ent, external_ref=ref, source="synthetic", status="analyzing", started_at=_recent(None, rng),
                    agent_id=agent.id if agent else None, queue=head.get("scenario", "")[:80], duration_s=round(total, 1))
        t = gap / 2
        for i, (r, d) in enumerate(zip(rows, durs)):
            call.turns.append(Turn(idx=i, speaker=ROLE.get(r.get("role"), "unknown"), start=round(t, 2), end=round(t + d, 2), text=r["text"].strip()))
            t += d + gap
        db.add(call)
        db.flush()
        if audio:
            _store(call, audio)
        _finish(db, call, analyze)
        created.append(call.id)
    db.commit()
    return created


def import_older_tts(db: Session, folder: Path, analyze: bool = True, gap_s: float = .35) -> list[str]:
    """Mohammed's older TTS calls: no full recording, so the clips are joined (with short pauses) into one."""
    rng = random.Random("synthetic-old")
    dialogues = {}
    dpath = folder / "scripts" / "dialogues.jsonl"
    if dpath.is_file():
        for line in dpath.read_text(encoding="utf-8").splitlines():
            if line.strip():
                d = json.loads(line)
                dialogues[d["id"]] = d
    created = []
    tmp = storage.root() / "_tmp"
    tmp.mkdir(parents=True, exist_ok=True)
    for cid, rows in sorted(_rows_by_call(folder / "turns.jsonl").items()):
        ent = _enterprise_of(" ".join(r["text"] for r in rows))
        ref = f"synthetic:{cid}"
        if _exists(db, ent, ref):
            continue
        d = dialogues.get(cid.removeprefix("syn_"), {})
        pieces, sr, t = [], None, 0.0
        call = Call(enterprise_id=ent, external_ref=ref, source="synthetic", status="analyzing", started_at=_recent(None, rng),
                    queue=(d.get("scenario") or "")[:80])
        agent = _agent(db, ent, (d.get("agent") or {}).get("name", ""))
        call.agent_id = agent.id if agent else None
        for i, r in enumerate(rows):
            clip = folder / "turns" / r["file"]
            if not clip.is_file():
                continue
            x, s = sf.read(str(clip), dtype="float32", always_2d=True)
            sr = sr or s
            if s != sr:
                continue
            x = x.mean(axis=1)
            call.turns.append(Turn(idx=len(call.turns), speaker=ROLE.get(r.get("role"), "unknown"), start=round(t, 2),
                                   end=round(t + len(x) / sr, 2), text=r["text"].strip()))
            pieces += [x, np.zeros(int(gap_s * sr), dtype="float32")]
            t += len(x) / sr + gap_s
        if not call.turns:
            continue
        call.duration_s = round(t, 1)
        db.add(call)
        db.flush()
        joined = tmp / f"{cid}.wav"
        sf.write(str(joined), np.concatenate(pieces), sr)
        _store(call, joined)
        joined.unlink()
        _finish(db, call, analyze)
        created.append(call.id)
    db.commit()
    return created


# --------------------------------------------------------------------------------------------- audio for the 76 demo calls
def attach_demo_audio(db: Session, folder: Path, scripts: Path, version: int = 1) -> int:
    """Give the 76 script-only demo calls their phone-quality recording and the exact turn timings.
    Matches each demo call to its script by the transcript text (B.TECH demo calls were renamed after the phone)."""
    sig = {}
    for f in scripts.glob("hs*.txt"):
        lines = [t for k, t in parse_script(f.read_text(encoding="utf-8"))["lines"] if k != "hold"]
        sig["\n".join(lines)[:400]] = f.stem
    by_sid = {}
    for call in db.query(Call).filter(Call.source == "seed"):
        k = "\n".join(t.text for t in sorted(call.turns, key=lambda t: t.idx))[:400]
        if k in sig:
            by_sid[sig[k]] = call
    done = 0
    for line in (folder / "calls.jsonl").read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        call = by_sid.get(rec["call"])
        if rec.get("version") != version or not call or call.audio_path:
            continue
        audio = folder / rec["audio"]
        if not audio.is_file():
            continue
        segs = [s for s in rec["segments"] if not s.get("backchannel")]
        turns = sorted(call.turns, key=lambda t: t.idx)
        if len(segs) == len(turns):                      # same turns in the same order: take the real timings
            for t, s in zip(turns, segs):
                t.start, t.end = round(float(s["start"]), 2), round(float(s["end"]), 2)
        else:
            log.warning("%s: %d segments vs %d turns, keeping estimated timings", rec["call"], len(segs), len(turns))
        _store(call, audio)
        call.duration_s = round(float(rec.get("duration") or sf.info(str(audio)).duration), 1)
        call.metrics = measure(call.turns)
        done += 1
    db.commit()
    return done
