#!/usr/bin/env python3
"""
Migration 008 — cook_log: tillagningsdagbok per receptversion.

En rad i cook_log hör till en specifik version av ett recept och håller koll på
om versionen är *planerad* för tillagning eller redan *lagad och utvärderad*.

Konvention (samma som recipe_annotation): version_number = 0 betyder den live/
aktuella versionen (recipe-raden), N > 0 pekar på snapshot recipe_version.N.

  status='planned'  → menad för framtida tillagning/utvärdering
  status='cooked'   → tillagad; cooked_at + valfritt rating (1–5) + notes

UNIQUE(recipe_id, version_number): en version har högst en logg-rad som flippar
planned → cooked. När ett recept får en ny version flyttas v0-raden till sitt
frysta snapshot-nummer av apply_recipe_edit() i app.py.

Idempotent: bail:ar om tabellen redan finns.

Använd som: python scripts/migrations/008_cook_log.py [db_path]
"""
from __future__ import annotations
import os
import sys
import sqlite3

DB_PATH = os.environ.get("DB_PATH", "recipe.db")


def main() -> int:
    db_path = sys.argv[1] if len(sys.argv) > 1 else DB_PATH
    if not os.path.exists(db_path):
        print(f"DB saknas: {db_path}", file=sys.stderr)
        return 1
    con = sqlite3.connect(db_path)
    try:
        cur = con.cursor()
        existing = cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='cook_log'"
        ).fetchone()
        if existing:
            print("cook_log finns redan — hoppar över.")
            return 0
        cur.executescript(
            """
            CREATE TABLE cook_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id INTEGER NOT NULL REFERENCES recipe(id) ON DELETE CASCADE,
                version_number INTEGER NOT NULL,
                status TEXT NOT NULL CHECK (status IN ('planned','cooked')),
                cooked_at TEXT,
                rating INTEGER CHECK (rating IS NULL OR rating BETWEEN 1 AND 5),
                notes TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (recipe_id, version_number)
            );
            CREATE INDEX idx_cook_log_recipe ON cook_log(recipe_id, version_number);
            CREATE INDEX idx_cook_log_status ON cook_log(status);
            """
        )
        con.commit()
        print("cook_log skapad.")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
