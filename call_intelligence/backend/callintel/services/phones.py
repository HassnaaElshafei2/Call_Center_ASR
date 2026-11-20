"""Egyptian phone numbers: find them in recording names or transcripts, normalise, hash and mask.

Formats seen in the data (B.TECH recording names are the customer's number):
    01272729111      local mobile (11 digits, starts 010/011/012/015)
    201029240321     country code 20 + mobile without its leading 0
    1000470080       mobile without its leading 0 (10 digits)
"""
import hashlib
import hmac
import re

from ..config import settings

MOBILE_PREFIXES = ("10", "11", "12", "15")
_DIGITS = re.compile(r"\d+")
AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize(raw: str) -> str | None:
    """Any of the formats above (spaces, +, dashes, Arabic digits allowed) -> '+20XXXXXXXXXX', else None."""
    d = "".join(_DIGITS.findall((raw or "").translate(AR_DIGITS)))
    if d.startswith("0020"):
        d = d[4:]
    elif d.startswith("20") and len(d) == 12:
        d = d[2:]
    elif d.startswith("0") and len(d) == 11:
        d = d[1:]
    if len(d) == 10 and d[:2] in MOBILE_PREFIXES:
        return "+20" + d
    return None


def from_filename(name: str, rules: list[dict] | None = None) -> str | None:
    """Phone from a recording name. Rules (per enterprise) are regexes with a named group 'phone';
    without rules, any 10-12 digit run that is a valid mobile counts."""
    stem = re.sub(r"\.[A-Za-z0-9]{2,4}$", "", name or "")
    for r in rules or []:
        m = re.search(r.get("pattern", ""), stem)
        if m and m.groupdict().get("phone"):
            p = normalize(m.group("phone"))
            if p:
                return p
    if rules:
        return None
    for run in re.findall(r"\d{10,12}", stem):
        p = normalize(run)
        if p:
            return p
    return None


def hash_phone(e164: str) -> str:
    return hmac.new(settings().phone_hash_key.encode(), e164.encode(), hashlib.sha256).hexdigest()


def mask(e164: str) -> str:
    """'+201029240321' -> '+20 10 •••• 0321'"""
    d = e164[3:]
    return f"+20 {d[:2]} •••• {d[-4:]}" if len(d) == 10 else "•••"


def pretty(e164: str) -> str:
    d = e164[3:]
    return f"+20 {d[:2]} {d[2:6]} {d[6:]}" if len(d) == 10 else e164
