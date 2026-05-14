#!/usr/bin/env python3
"""
Migration 005 — döp om menu→kitchen och section→type, ta bort image_url.

Idempotent: bail:ar med "already migrated" om recipe-tabellen redan har
kolumnen `kitchen` (och saknar `menu`).

Ändringar:
  recipe:          kolumnen `image_url` tas bort.
                   `section` → `type`, `menu` → `kitchen`.
  recipe_version:  kolumnen `image_url` tas bort.
                   `section` → `type`, `menu` → `kitchen`.
  recipe_with_ingredients: VIEW byggs om med nya kolumnnamn.

Data bevaras: värdena i menu kopieras till kitchen, section → type.

Använd som: python scripts/migrations/005_kitchen_type_no_image.py [db_path]
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def is_already_migrated(conn: sqlite3.Connection) -> bool:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(recipe)").fetchall()}
    return "kitchen" in cols and "menu" not in cols


def counts(conn: sqlite3.Connection) -> dict:
    c = conn.cursor()
    return {
        "recipe": c.execute("SELECT COUNT(*) FROM recipe").fetchone()[0],
        "recipe_version": c.execute("SELECT COUNT(*) FROM recipe_version").fetchone()[0],
        "ingredient": c.execute("SELECT COUNT(*) FROM ingredient").fetchone()[0],
        "recipe_ingredient": c.execute("SELECT COUNT(*) FROM recipe_ingredient").fetchone()[0],
    }


def migrate(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN")

    # Dependent view first. (Or table — local dev had it as a TABLE in some
    # branches; handle both.)
    obj = conn.execute(
        "SELECT type FROM sqlite_master WHERE name='recipe_with_ingredients'"
    ).fetchone()
    if obj:
        kind = obj[0]
        conn.execute(f"DROP {kind.upper()} IF EXISTS recipe_with_ingredients")

    # --- recipe ---
    conn.execute("""
        CREATE TABLE recipe_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL CHECK (length(TRIM(title)) > 0),
            description TEXT,
            instructions TEXT,
            notes TEXT,
            tags TEXT,
            type TEXT,
            kitchen TEXT
        )
    """)
    conn.execute("""
        INSERT INTO recipe_new (id, title, description, instructions, notes,
                                tags, type, kitchen)
        SELECT id, title, description, instructions, notes,
               tags, section, menu
        FROM recipe
    """)
    conn.execute("DROP TABLE recipe")
    conn.execute("ALTER TABLE recipe_new RENAME TO recipe")

    # --- recipe_version ---
    conn.execute("""
        CREATE TABLE recipe_version_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL,
            version_number INTEGER NOT NULL,
            title TEXT,
            description TEXT,
            instructions TEXT,
            notes TEXT,
            tags TEXT,
            type TEXT,
            kitchen TEXT,
            ingredients_json TEXT,
            changed_at TEXT NOT NULL,
            changed_by TEXT,
            change_note TEXT,
            FOREIGN KEY (recipe_id) REFERENCES recipe(id)
        )
    """)
    conn.execute("""
        INSERT INTO recipe_version_new
            (id, recipe_id, version_number, title, description, instructions,
             notes, tags, type, kitchen, ingredients_json, changed_at,
             changed_by, change_note)
        SELECT id, recipe_id, version_number, title, description, instructions,
               notes, tags, section, menu, ingredients_json, changed_at,
               changed_by, change_note
        FROM recipe_version
    """)
    conn.execute("DROP TABLE recipe_version")
    conn.execute("ALTER TABLE recipe_version_new RENAME TO recipe_version")

    # Indexes.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_recipe_version_recipe "
        "ON recipe_version(recipe_id, version_number)"
    )

    # Reseed sqlite_sequence for renamed tables.
    for table in ("recipe", "recipe_version"):
        max_id = conn.execute(
            f"SELECT COALESCE(MAX(id), 0) FROM {table}"
        ).fetchone()[0]
        conn.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))
        conn.execute(
            "INSERT INTO sqlite_sequence(name, seq) VALUES (?, ?)",
            (table, max_id),
        )

    # Rebuild VIEW with new column names, no image_url.
    conn.execute("""
        CREATE VIEW recipe_with_ingredients AS
        SELECT
            r.id AS recipe_id, r.title, r.description, r.instructions,
            r.notes, r.tags, r.type, r.kitchen,
            i.id AS ingredient_id, i.name AS ingredient_name,
            i.grocery_category, i.kitchen_staple,
            ri.amount, ri.unit, ri.note AS ingredient_note
        FROM recipe r
        LEFT JOIN recipe_ingredient ri ON ri.recipe_id = r.id
        LEFT JOIN ingredient i ON i.id = ri.ingredient_id
    """)

    conn.execute("COMMIT")
    conn.execute("PRAGMA foreign_keys = ON")

    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(f"FK violations after migration: {violations}")


def main() -> int:
    db_path = Path(sys.argv[1] if len(sys.argv) > 1 else "recipe.db")
    if not db_path.exists():
        print(f"✗ DB not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path), isolation_level=None)

    if is_already_migrated(conn):
        print("✓ Already migrated (recipe has 'kitchen', no 'menu'). No-op.")
        return 0

    before = counts(conn)
    print(f"--- BEFORE ({db_path}) ---")
    for k, v in before.items():
        print(f"  {k}: {v}")

    try:
        migrate(conn)
    except Exception as e:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.OperationalError:
            pass
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        return 1

    after = counts(conn)
    print(f"\n--- AFTER ---")
    for k, v in after.items():
        marker = " ✗ changed!" if before[k] != v else ""
        print(f"  {k}: {v}{marker}")

    if any(before[k] != after[k] for k in before):
        print("\n✗ Row counts changed — investigate!", file=sys.stderr)
        return 2

    print("\n✓ Migration successful.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
