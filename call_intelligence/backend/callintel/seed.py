"""Starting data: the two enterprises, their call categories and QA scorecards, the first users.
Also the demo data (our 76 synthetic call scripts) and an importer for labelled real calls."""
from __future__ import annotations

import hashlib
import json
import random
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from .config import settings
from .models import Agent, Call, Category, Customer, Enterprise, Membership, Scorecard, Team, Turn, User
from .security import hash_password
from .services import identity, jobs

ENTERPRISES = [
    {"id": "adib", "name": "ADIB Egypt", "name_ar": "مصرف أبوظبي الإسلامي", "kind": "bank", "accent": "#0f7b6c",
     "filename_rules": []},
    {"id": "btech", "name": "B.TECH", "name_ar": "بي تك", "kind": "electronics retailer", "accent": "#e4572e",
     # recording names are the customer's number: btech_01272729111, btech_201029240321, btech_1000470080
     "filename_rules": [{"pattern": r"btech_(?P<phone>\d{10,12})", "note": "B.TECH recording name = customer phone"}]},
]

CATEGORIES = {
    "adib": [
        ("card_blocked_lost", "Card blocked, lost or stolen", "الكارت اتقفل أو ضاع", "blocked by wrong PIN, lost/stolen card, replacement"),
        ("card_transaction_dispute", "Card transaction declined or disputed", "عملية على الكارت", "declined abroad, unknown online purchase, suspicious transaction"),
        ("card_fees_charges", "Card fees, interest and penalties", "مصاريف وغرامات الكارت", "annual fees, late penalties, minimum vs full payment"),
        ("credit_limit_installments", "Credit limit and card installments", "الحد الائتماني والتقسيط", "limit increase, installment plans on the card"),
        ("atm_issue", "ATM problem", "مشكلة ماكينة الصراف", "card retained, less cash dispensed"),
        ("transfer_instapay", "Transfers and InstaPay", "التحويلات وإنستاباي", "wrong recipient, fees, failed internal transfer"),
        ("deposit_salary", "Deposits and salary", "الإيداع والمرتب", "Fawry deposit not credited, salary not received"),
        ("app_otp_digital", "Mobile app, OTP and digital onboarding", "الأبلكيشن والرقم السري للمرة الواحدة", "OTP not received, app help, selfie verification"),
        ("account_services", "Account services and documents", "خدمات الحساب", "dormant account, ID update, phone change, statements, cheque book"),
        ("finance_products", "Financing, loans and certificates", "التمويل والشهادات", "personal finance, murabaha, early settlement, salary advance, certificate returns"),
        ("offers_cashback", "Offers and cashback", "العروض والكاش باك", "cashback offers and promotions"),
        ("complaint_follow_up", "Complaint or follow-up", "شكوى أو متابعة", "delayed complaint, long wait, bounced cheque, unhappy customer"),
    ],
    "btech": [
        ("product_inquiry", "Product, price and availability", "استفسار عن منتج وسعر", "prices, offers, branch availability, online vs branch price"),
        ("installments_financing", "Installments and financing", "التقسيط والتمويل", "buying on installments, documents, financing companies, mini cash, guarantor"),
        ("installment_payment", "Installment payments and penalties", "سداد الأقساط والغرامات", "due date, paying via Fawry or abroad, late penalties, early settlement, collections"),
        ("order_delivery", "Order status and delivery", "الطلب والتوصيل", "late delivery, address change, online order tracking, cancellation"),
        ("installation", "Installation", "التركيب", "AC/TV/heater installation appointments and extra charges"),
        ("maintenance_warranty", "Maintenance, repair and warranty", "الصيانة والضمان", "faults, technician no-show, spare parts, warranty and extended warranty"),
        ("returns_refunds", "Returns, exchanges and refunds", "الاسترجاع والاستبدال", "damaged or wrong item, refund of returned or cancelled order, trade-in"),
        ("payment_billing", "Payment and receipts", "الدفع والإيصالات", "split payment, missing receipt, extra amount charged, gift cards"),
        ("complaint_staff", "Complaint about staff or branch", "شكوى من موظف أو فرع", "staff behaviour, price-match requests, escalations"),
    ],
}

SCORECARDS = {
    "adib": [
        ("greeting", "Greeting and introduction", "agent greets, gives name and the bank's name", 1, False),
        ("verification", "Identity verification", "verifies the customer's identity before account or card details", 2, True),
        ("understanding", "Understands the need", "asks the right questions, restates the problem", 1, False),
        ("accuracy", "Correct information", "information and steps given are correct and clear", 2, True),
        ("empathy", "Empathy and courtesy", "polite, calm, acknowledges feelings, no blaming", 1, False),
        ("hold_etiquette", "Hold etiquette", "asks before holding and thanks the customer after", 0.5, False),
        ("resolution_effort", "Ownership of the problem", "solves it or gives a clear next step and timeline", 2, False),
        ("closing", "Closing", "offers more help, closes politely", 0.5, False),
    ],
    "btech": [
        ("greeting", "Greeting and introduction", "agent greets with B.TECH and their name, asks the customer's name", 1, False),
        ("understanding", "Understands the need", "asks the right questions (product, order, model, governorate)", 1, False),
        ("accuracy", "Correct information", "prices, policies and steps are correct; no false promises", 2, True),
        ("empathy", "Empathy and courtesy", "polite, calm, apologises when the company is at fault", 1, False),
        ("hold_etiquette", "Hold etiquette", "asks before holding and thanks the customer after", 0.5, False),
        ("resolution_effort", "Ownership of the problem", "solves it, escalates properly, or gives a clear next step", 2, False),
        ("sales_opportunity", "Sales opportunity", "offers a relevant product, warranty or financing when it fits", 0.5, False),
        ("closing", "Closing", "offers more help, mentions the call survey, closes politely", 0.5, False),
    ],
}

TEAMS = {"adib": ["Cards & Payments", "Digital & Accounts"], "btech": ["Sales", "After-sales"]}


def seed_base(db: Session, demo_users: bool = True) -> None:
    """Idempotent: creates what is missing, never overwrites edits."""
    for e in ENTERPRISES:
        if not db.get(Enterprise, e["id"]):
            db.add(Enterprise(**e))
    db.flush()
    for ent, cats in CATEGORIES.items():
        have = {c.code for c in db.query(Category).filter_by(enterprise_id=ent)}
        for code, name, ar, desc in cats:
            if code not in have:
                db.add(Category(enterprise_id=ent, code=code, name=name, name_ar=ar, description=desc))
    for ent, kpis in SCORECARDS.items():
        if not db.query(Scorecard).filter_by(enterprise_id=ent).first():
            db.add(Scorecard(enterprise_id=ent, version=1, active=True,
                             kpis=[{"code": c, "name": n, "description": d, "weight": w, "critical": cr}
                                   for c, n, d, w, cr in kpis]))
    for ent, names in TEAMS.items():
        for n in names:
            if not db.query(Team).filter_by(enterprise_id=ent, name=n).first():
                db.add(Team(enterprise_id=ent, name=n))
    s = settings()
    if not db.query(User).filter_by(email=s.admin_email).first():
        db.add(User(email=s.admin_email, name="Administrator", password_hash=hash_password(s.admin_password),
                    is_superadmin=True))
    db.flush()
    if demo_users:
        _demo_users(db)
    db.commit()


DEMO_USERS = [  # email, name, {enterprise: role}
    ("manager@demo.sia", "Nour Hassan (manager)", {"adib": "manager", "btech": "manager"}),
    ("qa@demo.sia", "Omar Fathy (QA)", {"adib": "qa", "btech": "qa"}),
    ("retention@demo.sia", "Mona Adel (retention)", {"adib": "retention", "btech": "retention"}),
    ("exec@demo.sia", "Karim Saleh (executive)", {"adib": "executive", "btech": "executive"}),
    ("btech.qa@demo.sia", "Salma Ali (B.TECH QA only)", {"btech": "qa"}),
]


def _demo_users(db: Session):
    pw = hash_password(__import__("os").environ.get("DEMO_PASSWORD", "demo-change-me"))
    for email, name, roles in DEMO_USERS:
        u = db.query(User).filter_by(email=email).first()
        if u:
            continue
        u = User(email=email, name=name, password_hash=pw)
        db.add(u)
        db.flush()
        for ent, role in roles.items():
            db.add(Membership(user_id=u.id, enterprise_id=ent, role=role))


# --------------------------------------------------------------------------------------------- demo calls
SPAN = re.compile(r"\{([^{}|]*)\|([^{}]*)\}")
WPS = 2.3
CAIRO = ZoneInfo("Africa/Cairo")


def parse_script(text: str) -> dict:
    head, lines = {}, []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            k, _, v = line[1:].partition(":")
            head[k.strip()] = v.strip()
            continue
        hold = re.match(r"\[HOLD\s+(\d+)\s*s?\]", line, re.I)
        if hold:
            lines.append(("hold", int(hold.group(1))))
            continue
        m = re.match(r"^(A2|A|C|I)\s*:\s*(.*)$", line)
        if m:
            spoken = SPAN.sub(lambda g: g.group(1), m.group(2)).strip()
            lines.append(({"A": "agent", "A2": "agent", "C": "customer", "I": "ivr"}[m.group(1)], spoken))
    return {"head": head, "lines": lines}


def _person(v: str) -> str:
    return re.sub(r"\s*\(.*\)\s*$", "", v or "").strip()


def _phone_for(name: str, salt: str) -> str:
    h = int(hashlib.sha256((salt + name).encode()).hexdigest(), 16)
    return "01" + "0125"[h % 4] + f"{h % 10**8:08d}"


def import_scripts(db: Session, folder: Path, days: int = 28, limit: int | None = None, analyze: bool = True) -> list[str]:
    """Each script becomes a finished-transcript call (no audio) spread over the last `days` days."""
    rng = random.Random(7)
    files = sorted(folder.glob("hs*.txt"))[:limit] if limit else sorted(folder.glob("hs*.txt"))
    now = datetime.now(timezone.utc)
    agents: dict[tuple[str, str], Agent] = {}
    teams = {(t.enterprise_id, i): t for ent in TEAMS for i, t in enumerate(db.query(Team).filter_by(enterprise_id=ent).order_by(Team.name))}
    created = []
    # a few customers call twice (repeat calls, Customer 360)
    # (same company, related problem: a late order and then a broken screen, a cancelled order and then its refund...)
    shared = {"hs53": "hs36", "hs30": "hs52", "hs41": "hs65", "hs05": "hs23", "hs01": "hs76"}
    phone_of: dict[str, str] = {}
    by_sid: dict[str, Call] = {}       # B.TECH calls are renamed after the phone, so keep them by script id
    for f in files:
        sid = f.stem
        if db.query(Call).filter_by(external_ref=f"demo:{sid}").first():
            continue
        sc = parse_script(f.read_text(encoding="utf-8"))
        ent = "btech" if any("بي تك" in t for _, t in sc["lines"] if isinstance(t, str)) else "adib"
        aname = _person(sc["head"].get("agent", "")) or "Agent"
        key = (ent, aname)
        if key not in agents:
            agents[key] = db.query(Agent).filter_by(enterprise_id=ent, name=aname).first() or \
                Agent(enterprise_id=ent, name=aname, code=f"EXT-{100 + len(agents)}",
                      team_id=teams.get((ent, len(agents) % 2), None) and teams[(ent, len(agents) % 2)].id)
            db.add(agents[key])
            db.flush()
        day = rng.randint(0, days - 1)
        local = (now.astimezone(CAIRO) - timedelta(days=day)).replace(hour=rng.choice([9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]),
                                                                       minute=rng.randint(0, 59), second=0, microsecond=0)
        started = local.astimezone(timezone.utc)
        if sid in shared.values():     # the follow-up call comes 2-6 days after the first
            first = next(k for k, v in shared.items() if v == sid)
            prev = by_sid.get(first)
            if prev:
                started = prev.started_at + timedelta(days=rng.randint(2, 6), hours=rng.randint(1, 5))
        call = Call(enterprise_id=ent, external_ref=f"demo:{sid}", agent_id=agents[key].id, started_at=started,
                    source="seed", status="analyzing", queue=sc["head"].get("scenario", "")[:80])
        t, idx = 0.0, 0
        for kind, val in sc["lines"]:
            if kind == "hold":
                t += float(val)
                continue
            dur = max(0.8, len(val.split()) / WPS)
            call.turns.append(Turn(idx=idx, speaker=kind, start=round(t, 2), end=round(t + dur, 2), text=val, confidence=None))
            t += dur + rng.uniform(0.2, 0.8)
            idx += 1
        call.duration_s = round(t, 1)
        db.add(call)
        db.flush()
        if ent == "btech":            # B.TECH recordings are named by the customer's phone
            cname = _person(sc["head"].get("customer", ""))
            phone = phone_of.get(next((k for k, v in shared.items() if v == sid), ""), None) or _phone_for(cname, sid)
            phone_of[sid] = phone
            fmt = rng.choice(["local", "intl", "short"])
            call.external_ref = "btech_" + {"local": phone, "intl": "20" + phone[1:], "short": phone[1:]}[fmt]
            cust = identity.from_recording_name(db, call)
            call.customer_id = cust.id if cust else None
        elif sid in shared or sid in shared.values():   # ADIB: no phone in the name; the demo links the pair by account
            first = sid if sid in shared else next(k for k, v in shared.items() if v == sid)
            prev = by_sid.get(first)
            if prev and prev.customer_id and prev.id != call.id:
                call.customer_id = prev.customer_id
            else:
                cust = Customer(enterprise_id=ent, name=_person(sc["head"].get("customer", "")) or None,
                                identified_by="account")
                db.add(cust)
                db.flush()
                call.customer_id = cust.id
        by_sid[sid] = call
        if analyze:
            jobs.enqueue(db, "analyze_call", {"call_id": call.id}, max_attempts=3)
        else:
            call.status = "waiting_asr"
        created.append(call.id)
    db.commit()
    return created


def import_labelled(db: Session, folder: Path, enterprise: str, analyze: bool = True) -> list[str]:
    """Real calls with turn labels in the callcenter_data format: <folder>/turns.jsonl rows
    {call, role, file, text}, clips in <folder>/turns/, full recordings in <folder>/calls/<call>.mp3|wav.
    Turn times come from the clip lengths (laid end to end)."""
    import soundfile as sf
    from .services import storage
    rows = [json.loads(l) for l in (folder / "turns.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    by: dict[str, list[dict]] = {}
    for r in rows:
        by.setdefault(r["call"], []).append(r)
    created = []
    for cid, rs in by.items():
        if db.query(Call).filter_by(enterprise_id=enterprise, external_ref=cid).first():
            continue
        call = Call(enterprise_id=enterprise, external_ref=cid, source="import", status="analyzing")
        m = re.match(r"(20\d{6})(\d{6})", cid)
        if m:
            call.started_at = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=CAIRO).astimezone(timezone.utc)
        t = 0.0
        for i, r in enumerate(rs):
            clip = folder / "turns" / r.get("file", "")
            dur = sf.info(str(clip)).duration if clip.is_file() else max(0.8, len(r["text"].split()) / WPS)
            call.turns.append(Turn(idx=i, speaker={"agent": "agent", "customer": "customer", "ivr": "ivr"}.get(r.get("role"), "unknown"),
                                   start=round(t, 2), end=round(t + dur, 2), text=r["text"]))
            t += dur + 0.3
        call.duration_s = round(t, 1)
        db.add(call)
        db.flush()
        full = next(iter((folder / "calls").glob(cid + ".*")), None) if (folder / "calls").is_dir() else None
        if full:
            dest = storage.path_for(enterprise, call.id, full.name)
            dest.write_bytes(full.read_bytes())
            call.audio_path = storage.relative(dest)
        cust = identity.from_recording_name(db, call)
        call.customer_id = cust.id if cust else None
        if analyze:
            jobs.enqueue(db, "analyze_call", {"call_id": call.id})
        created.append(call.id)
    db.commit()
    return created
