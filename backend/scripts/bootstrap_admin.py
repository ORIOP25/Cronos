"""Bootstrap idempotente de admin default para ambiente local Docker.

Garante login previsível após arranque "do zero", criando:
  - Organization (se não existir)
  - OrganizationSettings + GridSettings com defaults
  - User admin (se não existir)

Ativado via BOOTSTRAP_DEFAULT_ADMIN=1.
Nunca usado em staging/produção.
"""

import os
from datetime import date, time
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app import models
from app.core.security import hash_password


def _build_sync_url(raw_url: str) -> str:
    base_url = raw_url.replace("+asyncpg", "").replace("+psycopg2", "")
    if base_url.startswith("postgres://"):
        base_url = base_url.replace("postgres://", "postgresql://", 1)
    return base_url


def bootstrap_admin() -> None:
    enabled = os.environ.get("BOOTSTRAP_DEFAULT_ADMIN", "0") == "1"
    if not enabled:
        print("[bootstrap_admin] Bootstrap desativado (BOOTSTRAP_DEFAULT_ADMIN!=1).")
        return

    admin_email = os.environ.get("BOOTSTRAP_ADMIN_EMAIL", "admin@horariozen.local").strip().lower()
    admin_password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD", "admin1234")
    admin_name = os.environ.get("BOOTSTRAP_ADMIN_NAME", "Admin Horario Zen").strip() or "Admin Horario Zen"
    org_name = os.environ.get("BOOTSTRAP_ORG_NAME", "Escola Demo Horario Zen").strip() or "Escola Demo Horario Zen"

    if len(admin_password) < 6:
        raise SystemExit("[bootstrap_admin] ERRO: BOOTSTRAP_ADMIN_PASSWORD deve ter pelo menos 6 caracteres.")

    raw_url = os.environ.get("DATABASE_URL", "")
    if not raw_url:
        raise SystemExit("[bootstrap_admin] ERRO: DATABASE_URL vazia — impossível fazer bootstrap.")

    base_url = _build_sync_url(raw_url)
    today = date.today()
    engine = create_engine(base_url)

    with Session(engine) as db:
        existing_admin = db.execute(
            select(models.User).where(models.User.email == admin_email)
        ).scalar_one_or_none()
        if existing_admin is not None:
            print(f"[bootstrap_admin] Admin default já existe: {admin_email}.")
            return

        org = db.execute(
            select(models.Organization).order_by(models.Organization.id.asc())
        ).scalar_one_or_none()
        if org is None:
            org = models.Organization(name=org_name, plan_status="active")
            db.add(org)
            db.flush()
            print(f"[bootstrap_admin] Organization criada: {org_name} (id={org.id}).")

        org_settings = db.execute(
            select(models.OrganizationSettings).where(models.OrganizationSettings.organization_id == org.id)
        ).scalar_one_or_none()
        if org_settings is None:
            org_settings = models.OrganizationSettings(
                organization_id=org.id,
                school_start_date=date(today.year, 9, 1),
                school_target_end_date=date(today.year + 1, 6, 30),
                school_hard_end_date=date(today.year + 1, 7, 31),
                repair_stability_window_days=14,
            )
            db.add(org_settings)
            db.flush()

        grid_settings = db.execute(
            select(models.OrganizationGridSettings).where(models.OrganizationGridSettings.organization_id == org.id)
        ).scalar_one_or_none()
        if grid_settings is None:
            grid_settings = models.OrganizationGridSettings(
                organization_id=org.id,
                lunch_window_start=time(12, 0),
                lunch_window_end=time(14, 0),
                lunch_min_duration_minutes=60,
            )
            db.add(grid_settings)

        default_admin = models.User(
            name=admin_name,
            email=admin_email,
            hashed_password=hash_password(admin_password),
            role=models.UserRole.admin,
            organization_id=org.id,
            is_active=True,
        )
        db.add(default_admin)
        db.commit()
        print(f"[bootstrap_admin] Admin default criado: {admin_email}.")


if __name__ == "__main__":
    bootstrap_admin()
