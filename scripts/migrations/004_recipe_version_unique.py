#!/usr/bin/env python3
"""
Migration 004 — dedupera version_number per recipe + lägg UNIQUE-constraint.

Bakgrund: QC fann att recipe_id=10 har två rader med version_number=1
(en från initial migration-backfill, en från en cowork-session). Strikt
sett ett historik-fel, men oskadligt eftersom UI:t bara läser senaste raden
per (recipe_id, version_number).

Fixet: renumrera dupletter så de blir kontinuerliga 1..N (i id-ordning),
och lägg UNIQUE(recipe_id, version_number) så att framtida bugg blockeras
i DB-motorn istället för att fångas av QC.

Idempotent (no-op om constraint redan finns).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def has_unique_constraint(conn: sqlite3.Connection) -> bool:
    rows = conn.execute(
        "SELECT sql FROM sqlite_master "
        "WHERE type='index' AND tbl_name='recipe_version' "
        "AND sql LIKE '%UNIQUE%recipe_id%version_number%'"
    ).fetchall()
    return bool(rows)


def dedupe_version_numbers(conn: sqlite3.Connection) -> int:
    """For each recipe_id with duplicate version_numbers, renumber all its
    versions to 1..N by id-order. Returns number of rows updated."""
    affected_recipes = [
        row[0] for row in conn.execute("""
            SELECT recipe_id FROM recipe_version
            GROUP BY recipe_id
            HAVING COUNT(DISTINCT version_number) < COUNT(*)
        """).fetchall()
    ]
    total_updated = 0
    for recipe_id in affected_recipes:
        rows = conn.execute(
            "SELECT id FROM recipe_version WHERE recipe_id = ? ORDER BY id",
            (recipe_id,),
        ).fetchall()
        for new_ver, (row_id,) in enumerate(rows, start=1):
            conn.execute(
                "UPDATE recipe_version SET version_number = ? WHERE id = ?",
                (new_ver, row_id),
            )
            total_updated += 1
    return total_updated


def add_unique_constraint(conn: sqlite3.Connection) -> None:
    """Rebuild recipe_version with UNIQUE(recipe_id, version_number).
    Standard SQLite migration pattern."""
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("""
        CREATE TABLE recipe_version_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL REFERENCES recipe(id) ON DELETE CASCADE,
            version_number INTEGER NOT NULL,
            title TEXT,
            description TEXT,
            instructions TEXT,
            notes TEXT,
            image_url TEXT,
            tags TEXT,
            section TEXT,
            menu TEXT,
            ingredients_json TEXT,
            changed_at TEXT NOT NULL,
            changed_by TEXT,
            change_note TEXT,
            UNIQUE (recipe_id, version_number)
        )
    """)
    conn.execute("""
        INSERT INTO recipe_version_new
        SELECT id, recipe_id, version_number, title, description, instructions,
               notes, image_url, tags, section, menu, ingredients_json,
               changed_at, changed_by, change_note
        FROM recipe_version
    """)
    conn.execute("DROP TABLE recipe_version")
    conn.execute("ALTER TABLE recipe_version_new RENAME TO recipe_version")
    conn.execute(
        "CREATE INDEX idx_recipe_version_recipe "
        "ON recipe_version(recipe_id, version_number)"
    )
    # Reseed sequence (table was dropped, sqlite_sequence row removed).
    max_id = conn.execute(
        "SELECT COALESCE(MAX(id), 0) FROM recipe_version"
    ).fetchone()[0]
    conn.execute("DELETE FROM sqlite_sequence WHERE name = 'recipe_version'")
    conn.execute(
        "INSERT INTO sqlite_sequence(name, seq) VALUES (?, ?)",
        ("recipe_version", max_id),
    )
    conn.execute("PRAGMA foreign_keys = ON")


def main() -> int:
    db_path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/recipe.db")
    if not db_path.exists():
        print(f"✗ DB not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path), isolation_level=None)

    if has_unique_constraint(conn):
        print("✓ recipe_version already has UNIQUE(recipe_id, version_number). No-op.")
        return 0

    before = conn.execute("SELECT COUNT(*) FROM recipe_version").fetchone()[0]
    try:
        conn.execute("BEGIN")
        renumbered = dedupe_version_numbers(conn)
        add_unique_constraint(conn)
        conn.execute("COMMIT")
    except Exception as e:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.OperationalError:
            pass
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        return 1

    after = conn.execute("SELECT COUNT(*) FROM recipe_version").fetchone()[0]
    if before != after:
        print(f"✗ Row count changed: {before} → {after}", file=sys.stderr)
        return 2

    print(f"✓ Renumbered {renumbered} version row(s), added UNIQUE constraint.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
