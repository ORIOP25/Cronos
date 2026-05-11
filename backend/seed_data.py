import argparse
import sys
import subprocess
from sqlalchemy import text
from app.db.database import engine_sync

def reset_db():
    print("\n[seed_data] Resetting database (dropping public schema)...")
    with engine_sync.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public;"))
        conn.commit()
    print("[seed_data] Schema reset successfully.")

def run_migrations():
    print("[seed_data] Running Alembic migrations...")
    subprocess.run(["alembic", "upgrade", "head"], check=True)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Aperius Seed Data Dispatcher")
    parser.add_argument("--profile", required=True, choices=["small-realistic", "large-scale", "operational"], help="Seed profile to run")
    parser.add_argument("--reset", action="store_true", help="Reset database before seeding")
    args = parser.parse_args()

    try:
        if args.reset:
            reset_db()
            run_migrations()
        
        if args.profile == "small-realistic":
            import seed_data_small_realistic
            seed_data_small_realistic.run_seed()
        elif args.profile == "large-scale":
            print("[seed_data] Error: large-scale seed script is currently empty/unavailable.")
            sys.exit(1)
        elif args.profile == "operational":
            import seed_data_operational
            # Note: assuming seed_data_operational has a run_seed or similar. 
            # If it's empty, it will fail or do nothing.
            print("[seed_data] Running operational seed...")
            # For now, if it's empty, we just skip.
    except Exception as exc:
        print(f"\n[seed_data] ERROR: {exc}")
        sys.exit(1)
