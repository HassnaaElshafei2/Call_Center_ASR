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
