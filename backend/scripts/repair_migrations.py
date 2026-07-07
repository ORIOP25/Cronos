"""
Repair Alembic migration state.

When old migration files are deleted and replaced with a new baseline,
the alembic_version table in PostgreSQL may still reference a revision
that no longer exists on disk. This causes 'alembic upgrade head' to fail
with "Can't locate revision identified by '...'".

This script:
1. Reads the current revision stamped in the DB.
2. Checks if that revision exists in Alembic's known revisions.
3. If not, drops the alembic_version table so that 'alembic upgrade head'
   can run the baseline migration from scratch.
"""

import sys
import os

# Ensure the backend root is on the path so we can import app.*
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text
from alembic.config import Config
from alembic.script import ScriptDirectory
from app.db.database import engine_sync


def get_alembic_config() -> Config:
    """Return an Alembic Config pointing at alembic.ini."""
    ini_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini")
    return Config(ini_path)


def get_known_revisions(config: Config) -> set[str]:
    """Return all revision identifiers known on disk."""
    script = ScriptDirectory.from_config(config)
    return {rev.revision for rev in script.walk_revisions()}


def main() -> None:
    config = get_alembic_config()
    known = get_known_revisions(config)
    print(f"[repair] Revisoes conhecidas em disco: {known}")

    with engine_sync.connect() as conn:
        # Check if alembic_version table exists
        result = conn.execute(
            text(
                "SELECT EXISTS ("
                "  SELECT FROM information_schema.tables"
                "  WHERE table_name = 'alembic_version'"
                ")"
            )
        )
        table_exists = result.scalar()

        if not table_exists:
            print("[repair] Tabela alembic_version nao existe. Nada a reparar.")
            return

        # Read current stamped revision
        result = conn.execute(text("SELECT version_num FROM alembic_version"))
        rows = result.fetchall()

        if not rows:
            print("[repair] Tabela alembic_version esta vazia. Nada a reparar.")
            return

        stamped = {row[0] for row in rows}
        print(f"[repair] Revisao(oes) na BD: {stamped}")

        stale = stamped - known
        if not stale:
            print("[repair] Todas as revisoes na BD existem em disco. Tudo OK.")
            return

        print(f"[repair] Revisoes orfas encontradas: {stale}")
        print("[repair] A remover tabela alembic_version para permitir re-migracao...")

        conn.execute(text("DROP TABLE alembic_version"))
        conn.commit()

        print("[repair] Tabela alembic_version removida com sucesso.")


if __name__ == "__main__":
    main()
