"""Fix stale trigger for scheduler_state_version_events.

The SAME_TENANT_REFS in the baseline migration referenced columns (job_id,
draft_id, actor_user_id) that no longer exist on the table.  This script
recreates the trigger function with the correct columns:
  - school_year_id -> scheduler_school_year
  - changed_by_user_id -> user
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text
from app.db.database import engine_sync

SQL = """
CREATE OR REPLACE FUNCTION app_security.validate_scheduler_state_version_events_tenant_refs()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = pg_catalog, public
AS $$
BEGIN
    IF NEW."school_year_id" IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM public."scheduler_school_year" ref
        WHERE ref.id = NEW."school_year_id"
          AND ref.organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'Tenant mismatch for scheduler_state_version_events.school_year_id';
    END IF;

    IF NEW."changed_by_user_id" IS NOT NULL AND NOT EXISTS (
        SELECT 1 FROM public."user" ref
        WHERE ref.id = NEW."changed_by_user_id"
          AND ref.organization_id = NEW.organization_id
    ) THEN
        RAISE EXCEPTION 'Tenant mismatch for scheduler_state_version_events.changed_by_user_id';
    END IF;
    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_scheduler_state_version_events_tenant_refs
    ON public."scheduler_state_version_events";

CREATE TRIGGER trg_scheduler_state_version_events_tenant_refs
BEFORE INSERT OR UPDATE ON public."scheduler_state_version_events"
FOR EACH ROW
EXECUTE FUNCTION app_security.validate_scheduler_state_version_events_tenant_refs();
"""


def main():
    with engine_sync.connect() as conn:
        conn.execute(text(SQL))
        conn.commit()
    print("[fix] Trigger scheduler_state_version_events corrigido com sucesso.")


if __name__ == "__main__":
    main()
