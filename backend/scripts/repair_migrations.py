"""Reparação de estado inconsistente de migrações Alembic.

Casos tratados:
  1. Tabelas reais existem mas alembic_version não → stamp head.
  2. alembic_version existe mas tabelas core (user) nunca foram criadas
     e não há outras tabelas → stamp base e re-upgrade.
  3. alembic_version existe, tabelas core faltam e há schema parcial → erro manual.
"""

import os
import subprocess
from sqlalchemy import create_engine, text


def _build_sync_url(raw_url: str) -> str:
    """Converte qualquer DATABASE_URL para URL síncrono PostgreSQL."""
    base_url = raw_url.replace("+asyncpg", "").replace("+psycopg2", "")
    if base_url.startswith("postgres://"):
        base_url = base_url.replace("postgres://", "postgresql://", 1)
    return base_url


def _check_table_exists(engine, table_name: str) -> bool:
    with engine.connect() as conn:
        return bool(
            conn.execute(
                text("""
                    SELECT EXISTS (
                        SELECT 1 FROM information_schema.tables
                        WHERE table_schema = 'public' AND table_name = :table_name
                    )
                """),
                {"table_name": table_name},
            ).scalar()
        )


def _count_non_version_tables(engine) -> int:
    with engine.connect() as conn:
        return (
            conn.execute(
                text("""
                    SELECT COUNT(*)
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name <> 'alembic_version'
                """)
            ).scalar()
            or 0
        )


def repair_migrations() -> None:
    """Repara estado inconsistente de migrações, se necessário."""
    raw_url = os.environ.get("DATABASE_URL", "")
    if not raw_url:
        print("[repair_migrations] DATABASE_URL vazia — a abortar.")
        return

    base_url = _build_sync_url(raw_url)
    engine = create_engine(base_url)

    has_org = _check_table_exists(engine, "organization")
    has_user = _check_table_exists(engine, "user")
    has_version = _check_table_exists(engine, "alembic_version")

    # Caso 1: schema existe mas alembic_version não
    if has_org and not has_version:
        print("[repair_migrations] Schema existente sem alembic_version — a aplicar stamp head.")
        subprocess.run(["alembic", "stamp", "head"], check=True)
        return

    # Caso 2: inconsistente — version existe mas schema real não
    if has_version and not has_user:
        non_version_count = _count_non_version_tables(engine)
        if non_version_count == 0:
            print("[repair_migrations] BD inconsistente detetada — a fazer reset para base.")
            subprocess.run(["alembic", "stamp", "base"], check=True)
            return
        else:
            raise SystemExit(
                "[repair_migrations] ERRO: alembic_version existe mas tabelas core faltam "
                "e foi detetado schema parcial. Intervenção manual necessária."
            )

    print("[repair_migrations] Estado de migrações OK — nada a reparar.")


def verify_migrations() -> None:
    """Hard guard: confirma que tabela 'user' existe após migrações."""
    raw_url = os.environ.get("DATABASE_URL", "")
    if not raw_url:
        raise SystemExit("[verify_migrations] ERRO: DATABASE_URL vazia após migrações.")

    base_url = _build_sync_url(raw_url)
    engine = create_engine(base_url)

    if not _check_table_exists(engine, "user"):
        raise SystemExit(
            "[verify_migrations] ERRO: migrações concluídas mas tabela 'user' continua em falta."
        )

    print("[verify_migrations] Tabela 'user' confirmada — OK.")


if __name__ == "__main__":
    repair_migrations()
