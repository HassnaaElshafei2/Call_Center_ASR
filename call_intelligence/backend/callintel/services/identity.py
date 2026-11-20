"""Who the customer is, without a customer file.

In order of trust:
  1. the recording name (per-enterprise rules; B.TECH names are the customer's phone number),
  2. a phone number the customer says in the call (from the analysis),
  3. a name said in the call: a *possible* match only, a person confirms it,
  4. nothing: the call gets its own unidentified customer.
"""
import re

from sqlalchemy.orm import Session

from ..models import Call, Customer, Enterprise
from . import phones


def find_or_create_by_phone(db: Session, enterprise_id: str, e164: str, source: str, name: str = "") -> Customer:
    h = phones.hash_phone(e164)
    c = db.query(Customer).filter_by(enterprise_id=enterprise_id, phone_hash=h).first()
    if c:
        if name and not c.name:
            c.name = name
        return c
    c = Customer(enterprise_id=enterprise_id, phone_hash=h, phone_masked=phones.mask(e164), phone_full=e164,
                 identified_by=source, name=name)
    db.add(c)
    db.flush()
    return c


def from_recording_name(db: Session, call: Call) -> Customer | None:
    ent = db.get(Enterprise, call.enterprise_id)
    p = phones.from_filename(call.external_ref, ent.filename_rules if ent else None)
    return find_or_create_by_phone(db, call.enterprise_id, p, "filename") if p else None


def _clean_name(name: str | None) -> str:
    name = re.sub(r"^(أستاذ[ةه]?|استاذ[ةه]?|مدام|دكتور[ةه]?|مستر|يا)\s+", "", (name or "").strip())
    return name[:120]


def possible_matches(db: Session, call: Call, name: str, limit: int = 3) -> list[dict]:
    if not name:
        return []
    first = name.split()[0]
    q = (db.query(Customer).filter(Customer.enterprise_id == call.enterprise_id, Customer.name.ilike(f"%{first}%"),
                                   Customer.id != (call.customer_id or "")).limit(limit))
    return [{"customer_id": c.id, "name": c.name, "phone": c.phone_masked} for c in q]


def link_customer(db: Session, call: Call, said: dict):
    """Attach the call to a customer using what the analysis heard (said = {"name", "phone"})."""
    name = _clean_name(said.get("name"))
    if call.customer_id:                                   # already known from the recording name
        cust = db.get(Customer, call.customer_id)
        if name and cust and not cust.name:
            cust.name = name
        call.customer = cust
        return
    e164 = phones.normalize(said.get("phone") or "")
    if e164:
        call.customer = find_or_create_by_phone(db, call.enterprise_id, e164, "transcript", name)
    else:
        call.customer = Customer(enterprise_id=call.enterprise_id, name=name, identified_by="none")
        db.add(call.customer)
    db.flush()
    call.customer_id = call.customer.id
