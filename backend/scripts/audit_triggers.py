"""Audit all tenant-ref trigger functions for column references."""
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import text
from app.db.database import engine_sync

SQL = """
SELECT proname, prosrc
FROM pg_proc p
JOIN pg_namespace n ON n.oid = p.pronamespace
WHERE n.nspname = 'app_security'
  AND proname LIKE 'validate_%_tenant_refs'
ORDER BY proname
"""

with engine_sync.connect() as conn:
    result = conn.execute(text(SQL))
    for row in result:
        name = row[0]
        src = row[1]
        refs = re.findall(r'NEW\."?(\w+)"?', src)
        # Filter out organization_id since it's always valid
        refs = [r for r in refs if r != 'organization_id']
        print(f"{name}: {refs}")
