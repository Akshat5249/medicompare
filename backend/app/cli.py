"""Operator CLI: python -m app.cli seed | import | publish | create-admin | seed-demo-users | retention | quality."""

from __future__ import annotations

import argparse
import getpass
import json
import os
from pathlib import Path

from sqlalchemy import select

from app.core import get_storage, hash_password
from app.db import session_factory
from app.imports import pipeline
from app.imports.seed import ensure_sources, seed
from app.models import DataSource, ImportBatch, PharmacistProfile, Role, User
from app.prescriptions.service import run_retention
from app.quality import run_quality_checks

DEMO_USERS = [
    ("demo.user@example.com", Role.user, "Demo User"),
    ("demo.pharmacist@example.com", Role.pharmacist, "Demo Pharmacist"),
    ("demo.admin@example.com", Role.admin, "Demo Admin"),
]


def _print(data: object) -> None:
    print(json.dumps(data, indent=2, default=str))


def _upsert_user(db, email: str, password: str, role: Role, name: str | None = None) -> User:  # type: ignore[no-untyped-def]
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email, password_hash=hash_password(password), role=role.value, display_name=name
        )
        db.add(user)
        db.flush()
    return user  # type: ignore[no-any-return]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("seed", help="Create the bucket and load real plus flagged demo data")
    stage = commands.add_parser("import", help="Stage and validate a CSV")
    stage.add_argument("source_code")
    stage.add_argument("kind")
    stage.add_argument("path", type=Path)
    publish = commands.add_parser("publish", help="Publish a validated batch")
    publish.add_argument("batch_id", type=int)
    admin = commands.add_parser("create-admin", help="Create an admin (password from a prompt)")
    admin.add_argument("email")
    commands.add_parser("seed-demo-users", help="Local demo accounts; refused in production")
    commands.add_parser("retention", help="Run the retention job once")
    commands.add_parser("quality", help="Run data-quality checks on published data")
    args = parser.parse_args()

    with session_factory()() as db:
        if args.command == "seed":
            get_storage().ensure_bucket()
            _print(seed(db))
        elif args.command == "import":
            ensure_sources(db)
            source = db.scalar(select(DataSource).where(DataSource.code == args.source_code))
            if source is None:
                parser.error(f"unknown source {args.source_code}")
            batch = pipeline.stage_rows(
                db,
                source=source,
                kind=args.kind,
                file_name=args.path.name,
                content=args.path.read_bytes(),
            )
            db.commit()
            _print(
                {
                    "batch_id": batch.id,
                    "rows": batch.row_count,
                    "valid": batch.valid_count,
                    "failed": batch.failed_count,
                }
            )
        elif args.command == "publish":
            found = db.get(ImportBatch, args.batch_id)
            if found is None:
                parser.error("unknown batch")
            result = pipeline.publish(db, found)
            pipeline.rebuild_lasa_pairs(db)
            db.commit()
            _print(result)
        elif args.command == "create-admin":
            password = getpass.getpass("Password (10+ characters): ")
            if len(password) < 10:
                parser.error("password too short")
            _upsert_user(db, args.email.lower(), password, Role.admin)
            db.commit()
            _print({"created": args.email})
        elif args.command == "seed-demo-users":
            if os.environ.get("APP_ENV") == "production":
                parser.error("demo users are refused in production")
            password = os.environ.get("DEMO_PASSWORD", "local-demo-only-password")
            for email, role, name in DEMO_USERS:
                user = _upsert_user(db, email, password, role, name)
                if role == Role.pharmacist and db.get(PharmacistProfile, user.id) is None:
                    db.add(
                        PharmacistProfile(
                            user_id=user.id,
                            registration_number="DEMO-0000",
                            state_council="Demo council (fictional)",
                            status="approved",
                        )
                    )
            db.commit()
            _print({"demo_users": [email for email, _, _ in DEMO_USERS]})
        elif args.command == "retention":
            _print(run_retention(db))
        elif args.command == "quality":
            report = run_quality_checks(db)
            _print(report)
            return 0 if report["passed"] else 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
