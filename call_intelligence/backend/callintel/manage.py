"""Command line.

    python -m callintel.manage init                       # migrate the database, create enterprises, categories, users
    python -m callintel.manage demo /path/to/scripts      # import the 76 synthetic calls and queue their analysis
    python -m callintel.manage import-labelled /path/to/callcenter_data/real/btech --enterprise btech
    python -m callintel.manage analyze-now [--workers 4]  # run queued jobs here until the queue is empty
    python -m callintel.manage create-user email "Name" password --role adib:manager --role btech:qa
"""
import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from alembic import command
from alembic.config import Config

from .db import session_scope
from .models import Membership, User
from .security import hash_password


def migrate():
    cfg = Config(str(Path(__file__).resolve().parent.parent / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parent.parent / "alembic"))
    command.upgrade(cfg, "head")


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(prog="callintel")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init")
    i.add_argument("--no-demo-users", action="store_true")
    d = sub.add_parser("demo")
    d.add_argument("scripts", type=Path)
    d.add_argument("--limit", type=int)
    d.add_argument("--days", type=int, default=28)
    li = sub.add_parser("import-labelled")
    li.add_argument("folder", type=Path)
    li.add_argument("--enterprise", required=True, choices=["adib", "btech"])
    imp = sub.add_parser("import-data", help="real calls, Mohammed's synthetic calls and the 76 demo recordings from Call_Center_Data")
    imp.add_argument("repo", type=Path)
    imp.add_argument("--keep-dates", action="store_true", help="keep the real calls' original recording dates")
    imp.add_argument("--no-analysis", action="store_true")
    imp.add_argument("--only", choices=["real", "synthetic", "demo-audio"], action="append")
    sub.add_parser("adopt-export", help="after loading a database export: passwords and phone matching from this .env")
    a = sub.add_parser("analyze-now")
    a.add_argument("--workers", type=int, default=4)
    u = sub.add_parser("create-user")
    u.add_argument("email")
    u.add_argument("name")
    u.add_argument("password")
    u.add_argument("--role", action="append", default=[], help="enterprise:role, e.g. btech:qa")
    u.add_argument("--superadmin", action="store_true")
    args = p.parse_args(argv)

    if args.cmd == "init":
        migrate()
        from .seed import seed_base
        with session_scope() as db:
            seed_base(db, demo_users=not args.no_demo_users)
        print("database ready")
    elif args.cmd == "demo":
        from .seed import import_scripts
        with session_scope() as db:
            ids = import_scripts(db, args.scripts, days=args.days, limit=args.limit)
        print(f"imported {len(ids)} calls; their analysis is queued (run the worker, or: manage analyze-now)")
    elif args.cmd == "import-labelled":
        from .seed import import_labelled
        with session_scope() as db:
            ids = import_labelled(db, args.folder, args.enterprise)
        print(f"imported {len(ids)} calls; their analysis is queued")
    elif args.cmd == "import-data":
        from . import importers
        root, an, only = args.repo, not args.no_analysis, set(args.only or ["real", "synthetic", "demo-audio"])
        with session_scope() as db:
            if "real" in only:
                for ent in ("adib", "btech"):
                    f = root / "callcenter_data" / "real" / ent
                    if f.is_dir():
                        print(f"real {ent}: {len(importers.import_real(db, f, ent, args.keep_dates, an))} calls")
            if "synthetic" in only:
                f = root / "callcenter_data" / "synthetic"
                if (f / "elevenlabs").is_dir():
                    print(f"synthetic ElevenLabs: {len(importers.import_elevenlabs(db, f / 'elevenlabs', an))} calls")
                if (f / "older_tts").is_dir():
                    print(f"synthetic older TTS: {len(importers.import_older_tts(db, f / 'older_tts', an))} calls")
            if "demo-audio" in only:
                f = root / "elevenlabs_hs_phone_v2" / "elevenlabs_hs_phone_v2"
                scripts = root / "elevenlabs_hs" / "elevenlabs_hs" / "scripts"
                if f.is_dir() and scripts.is_dir():
                    print(f"demo calls with audio: {importers.attach_demo_audio(db, f, scripts)}")
        print("done; analysis is queued for the new calls (run the worker, or: manage analyze-now)")
    elif args.cmd == "adopt-export":
        import os
        from .config import settings
        from .models import Customer
        from .seed import DEMO_USERS
        from .services.phones import hash_phone
        st = settings()
        with session_scope() as db:
            admin = db.query(User).filter_by(email=st.admin_email.lower()).first() or User(email=st.admin_email.lower(), name="Administrator")
            admin.password_hash, admin.is_superadmin = hash_password(st.admin_password), True
            db.add(admin)
            demo_pw = os.environ.get("DEMO_PASSWORD", "demo-change-me")
            for email, *_ in DEMO_USERS:
                u = db.query(User).filter_by(email=email).first()
                if u:
                    u.password_hash = hash_password(demo_pw)
            n = 0
            for cu in db.query(Customer).filter(Customer.phone_full != ""):
                cu.phone_hash, n = hash_phone(cu.phone_full), n + 1
        print(f"passwords set from this .env ({st.admin_email} and the demo users); {n} customer phone numbers re-keyed")
    elif args.cmd == "analyze-now":
        from .worker import run_one
        done = 0

        def drain():
            n = 0
            while run_one():
                n += 1
            return n
        with ThreadPoolExecutor(args.workers) as ex:
            done = sum(ex.map(lambda _: drain(), range(args.workers)))
        print(f"ran {done} jobs")
    elif args.cmd == "create-user":
        with session_scope() as db:
            user = db.query(User).filter_by(email=args.email.lower()).first() or User(email=args.email.lower(), name=args.name)
            user.name, user.password_hash, user.is_superadmin = args.name, hash_password(args.password), args.superadmin
            db.add(user)
            db.flush()
            for r in args.role:
                ent, role = r.split(":")
                db.query(Membership).filter_by(user_id=user.id, enterprise_id=ent).delete()
                db.add(Membership(user_id=user.id, enterprise_id=ent, role=role))
        print("saved", args.email)
    return 0


if __name__ == "__main__":
    sys.exit(main())
