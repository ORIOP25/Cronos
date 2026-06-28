from app.db.database import engine_sync
from sqlalchemy import text

with engine_sync.begin() as conn:
    conn.execute(text('DROP SCHEMA public CASCADE; CREATE SCHEMA public;'))
