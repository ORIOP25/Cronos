"""Canonical seed runner for Horario Zen.

This file is the single entrypoint for database seeding.
It uses the large-scale seed as default base profile and keeps data
consistent across sessions by default (non-destructive execution).

Usage examples:
    docker compose exec backend python seed_data.py
    docker compose exec backend python seed_data.py --reset
    docker compose exec backend python seed_data.py --profile baseline --reset
    docker compose exec backend python seed_data.py --profile operational --reset
    docker compose exec backend python seed_data.py --profile stress --reset
"""

from __future__ import annotations

import argparse
import math
import sys

from sqlalchemy import func, inspect, select, text

from app import models
from app.core.security import hash_password, verify_password
from app.db.database import Base, SessionLocalSync, engine_sync
from app.services.operational_seed_service import seed_operational_scenarios_sync

import seed_data_large_scale as large_scale_seed

PROFILE_LARGE_SCALE = "large-scale"
PROFILE_OPERATIONAL = "operational"
PROFILE_BASELINE = "baseline"
PROFILE_STRESS = "stress"

_LARGE_SCALE_DEFAULTS = {
    "ORG_COUNT": large_scale_seed.ORG_COUNT,
    "COURSES_PER_ORG": large_scale_seed.COURSES_PER_ORG,
    "SUBJECTS_PER_CLASS_MIN": large_scale_seed.SUBJECTS_PER_CLASS_MIN,
    "SUBJECTS_PER_CLASS_MAX": large_scale_seed.SUBJECTS_PER_CLASS_MAX,
    "MODULES_PER_SUBJECT_MIN": large_scale_seed.MODULES_PER_SUBJECT_MIN,
    "MODULES_PER_SUBJECT_MAX": large_scale_seed.MODULES_PER_SUBJECT_MAX,
    "MODULE_HOURS_MIN": large_scale_seed.MODULE_HOURS_MIN,
    "MODULE_HOURS_MAX": large_scale_seed.MODULE_HOURS_MAX,
}

PREFERRED_ALIAS_USERS = [
    {
        "name": "Ana Silva",
        "email": "ana.silva@escola.pt",
        "password": "1234",
        "role": models.UserRole.admin,
    },
]


def _apply_large_scale_configuration(profile: str) -> None:
    if profile in (PROFILE_LARGE_SCALE, PROFILE_STRESS):
        config = dict(_LARGE_SCALE_DEFAULTS)
    elif profile == PROFILE_BASELINE:
        config = {
            "ORG_COUNT": 1,
            "COURSES_PER_ORG": 2,
            "SUBJECTS_PER_CLASS_MIN": 6,
            "SUBJECTS_PER_CLASS_MAX": 7,
            "MODULES_PER_SUBJECT_MIN": 3,
            "MODULES_PER_SUBJECT_MAX": 4,
            "MODULE_HOURS_MIN": 24,
            "MODULE_HOURS_MAX": 32,
        }
    else:
        raise SystemExit(f"Unsupported large-scale profile configuration: {profile}")

    for key, value in config.items():
        setattr(large_scale_seed, key, value)

    classes_per_org = large_scale_seed.COURSES_PER_ORG * len(large_scale_seed.CLASS_BLUEPRINTS)
    teachers_per_subject_pool = math.ceil(classes_per_org / large_scale_seed.TEACHER_CLASS_RATIO)
    teachers_per_org = large_scale_seed.SUBJECTS_PER_CLASS_MAX * teachers_per_subject_pool

    rooms_per_org = math.ceil(classes_per_org / large_scale_seed.ROOMS_PER_CLASS_RATIO)
    rooms_gym_count = max(1, math.ceil(rooms_per_org * 0.05))
    rooms_lab_count = max(2, math.ceil(rooms_per_org * 0.25))
    rooms_normal_count = max(1, rooms_per_org - rooms_lab_count - rooms_gym_count)

    large_scale_seed.CLASSES_PER_ORG = classes_per_org
    large_scale_seed.TEACHERS_PER_SUBJECT_POOL = teachers_per_subject_pool
    large_scale_seed.TEACHERS_PER_ORG = teachers_per_org
    large_scale_seed.ROOMS_PER_ORG = rooms_per_org
    large_scale_seed.ROOMS_GYM_COUNT = rooms_gym_count
    large_scale_seed.ROOMS_LAB_COUNT = rooms_lab_count
    large_scale_seed.ROOMS_NORMAL_COUNT = rooms_normal_count

    large_scale_seed.ROOMS_TEMPLATE = (
        [
            {
                "name": f"Sala Normal {i:02d}",
                "capacity": 30,
                "type": large_scale_seed.RoomType.normal,
            }
            for i in range(1, rooms_normal_count + 1)
        ]
        + [
            {
                "name": f"Lab Informatica {i:02d}",
                "capacity": 24,
                "type": large_scale_seed.RoomType.lab,
            }
            for i in range(1, rooms_lab_count + 1)
        ]
        + [
            {
                "name": f"Espaco Educacao Fisica {i:02d}",
                "capacity": 60,
                "type": large_scale_seed.RoomType.gym,
            }
            for i in range(1, rooms_gym_count + 1)
        ]
    )


def _table_exists(table_name: str) -> bool:
    with engine_sync.connect() as conn:
        return bool(
            conn.execute(
                text(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = :table_name
                    )
                    """
                ),
                {"table_name": table_name},
            ).scalar()
        )


def _ensure_core_schema() -> None:
    if _table_exists("organization") and _table_exists("user"):
        return

    print("[seed] Core tables missing. Creating schema from current metadata...")
    Base.metadata.create_all(bind=engine_sync)


def _find_missing_schema_columns(limit: int = 20) -> list[str]:
    inspector = inspect(engine_sync)
    missing_columns: list[str] = []

    for table in Base.metadata.sorted_tables:
        table_name = table.name
        if not inspector.has_table(table_name):
            continue

        db_columns = {col["name"] for col in inspector.get_columns(table_name)}
        model_columns = {col.name for col in table.columns}

        for column_name in sorted(model_columns - db_columns):
            missing_columns.append(f"{table_name}.{column_name}")
            if len(missing_columns) >= limit:
                return missing_columns

    return missing_columns


def _assert_schema_compatible_for_seed() -> None:
    missing_columns = _find_missing_schema_columns()
    if not missing_columns:
        return

    preview = ", ".join(missing_columns[:8])
    if len(missing_columns) > 8:
        preview = f"{preview}, ..."

    raise RuntimeError(
        "Schema incompatível com os modelos atuais para seed sem reset. "
        "Execute 'docker compose exec backend alembic upgrade head' "
        "ou use 'python seed_data.py --profile large-scale --reset'. "
        f"Colunas em falta: {preview}"
    )


def _count_organizations(sync_db) -> int:
    return int(sync_db.execute(select(func.count(models.Organization.id))).scalar_one() or 0)


def _first_organization_id(sync_db) -> int | None:
    org = sync_db.execute(
        select(models.Organization).order_by(models.Organization.id.asc())
    ).scalars().first()
    if org is None:
        return None
    return int(org.id)


def _ensure_alias_logins() -> None:
    db = SessionLocalSync()
    try:
        org_id = _first_organization_id(db)
        if org_id is None:
            print("[seed] No organization found. Alias login sync skipped.")
            return

        created = 0
        updated = 0

        for alias in PREFERRED_ALIAS_USERS:
            user = db.execute(
                select(models.User).where(models.User.email == alias["email"])
            ).scalar_one_or_none()

            if user is None:
                db.add(
                    models.User(
                        name=alias["name"],
                        email=alias["email"],
                        hashed_password=hash_password(alias["password"]),
                        role=alias["role"],
                        organization_id=org_id,
                        is_active=True,
                    )
                )
                created += 1
                continue

            changed = False
            if alias["name"] and user.name != alias["name"]:
                user.name = alias["name"]
                changed = True
            if user.organization_id != org_id:
                user.organization_id = org_id
                changed = True
            if user.role != alias["role"]:
                user.role = alias["role"]
                changed = True
            if not user.is_active:
                user.is_active = True
                changed = True
            if not verify_password(alias["password"], user.hashed_password):
                user.hashed_password = hash_password(alias["password"])
                changed = True

            if changed:
                updated += 1

        if created or updated:
            db.commit()
        print(f"[seed] Alias logins synced (created={created}, updated={updated}).")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _run_large_scale_profile(*, reset: bool, profile: str) -> None:
    _apply_large_scale_configuration(profile)

    if reset:
        large_scale_seed.clean_database()
        large_scale_seed.create_tables()
    else:
        _ensure_core_schema()

    db = SessionLocalSync()
    try:
        org_count = _count_organizations(db)
    finally:
        db.close()

    if org_count > 0 and not reset:
        print("[seed] Existing organizations detected. Preserving data (no reset).")
    else:
        if not reset:
            _assert_schema_compatible_for_seed()
        print("[seed] Running large-scale profile...")
        large_scale_seed.run_seed()

    _ensure_alias_logins()


def _run_operational_profile(*, reset: bool) -> None:
    if reset:
        print("[seed] Resetting schema for operational profile...")
        Base.metadata.drop_all(bind=engine_sync)
        Base.metadata.create_all(bind=engine_sync)
    else:
        _ensure_core_schema()

    db = SessionLocalSync()
    try:
        org_count = _count_organizations(db)
        if org_count > 0 and not reset:
            print("[seed] Existing organizations detected. Preserving data (no reset).")
            return

        payload = seed_operational_scenarios_sync(db)
        db.commit()

        signature = payload["signature"]
        print("[seed] Operational profile completed.")
        print(f"[seed] profile={signature['profile']}")
        print(f"[seed] organization_count={signature['organization_count']}")
        print(f"[seed] scenario_codes={', '.join(signature['scenario_codes'])}")

    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Definitive seed runner. Defaults to large-scale profile and does not "
            "reset schema unless --reset is provided."
        )
    )
    parser.add_argument(
        "--profile",
        choices=[PROFILE_BASELINE, PROFILE_OPERATIONAL, PROFILE_LARGE_SCALE, PROFILE_STRESS],
        default=PROFILE_LARGE_SCALE,
        help="Seed profile to execute.",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate schema before seeding.",
    )
    return parser.parse_args()


def main() -> None:
    args = _parse_args()

    print("=" * 72)
    print("  Horario Zen - Definitive Seed Runner")
    print(f"  profile={args.profile} | reset={args.reset}")
    print("=" * 72)

    try:
        if args.profile in (PROFILE_BASELINE, PROFILE_LARGE_SCALE, PROFILE_STRESS):
            _run_large_scale_profile(reset=args.reset, profile=args.profile)
        elif args.profile == PROFILE_OPERATIONAL:
            _run_operational_profile(reset=args.reset)
        else:
            raise SystemExit(f"Unsupported profile: {args.profile}")

        print("\n[OK] Seed execution finished.")
        print("[INFO] Login alias available: ana.silva@escola.pt / 1234")
        print("[INFO] For a fresh deterministic load, use: python seed_data.py --reset")
    except Exception as exc:
        print(f"\n[ERROR] Seed execution failed: {exc}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
