#!/usr/bin/env python3
"""
Migration: Drop old recommendation_results data and create rec_snapshots table.

Usage:
    python scripts/migrate_rec_snapshots.py

This script:
1. Drops all rows from the old recommendation_results table
2. Creates the new rec_snapshots table with clean, indexed columns
3. Does NOT drop the old table (kept for import compat)
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.storage.database import engine, Base
from src.graph.models import RecSnapshot, RecommendationResult  # noqa — triggers table registration
from sqlalchemy import text

def main():
    with engine.connect() as conn:
        # 1. Purge old recommendation_results rows
        result = conn.execute(text("DELETE FROM recommendation_results"))
        print(f"[1/3] Purged {result.rowcount} rows from recommendation_results")

        # 2. Drop rec_snapshots if exists (clean slate)
        conn.execute(text("DROP TABLE IF EXISTS rec_snapshots CASCADE"))
        print("[2/3] Dropped old rec_snapshots table (if existed)")

        conn.commit()

    # 3. Create rec_snapshots with SQLAlchemy
    RecSnapshot.__table__.create(engine, checkfirst=True)
    print("[3/3] Created rec_snapshots table with indexes")

    # Verify
    with engine.connect() as conn:
        row = conn.execute(text(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'rec_snapshots' ORDER BY ordinal_position"
        ))
        cols = row.fetchall()
        print(f"\nrec_snapshots columns ({len(cols)}):")
        for name, dtype in cols:
            print(f"  {name:25s} {dtype}")

    print("\nMigration complete.")


if __name__ == "__main__":
    main()
