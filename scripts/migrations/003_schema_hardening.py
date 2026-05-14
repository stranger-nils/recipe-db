#!/usr/bin/env python3
"""
Fas B — schema-härdning. Kräver att 002 körts (data är ren).

Idempotent: bail:ar med "already hardened" om recipe.id redan är
INTEGER PRIMARY KEY AUTOINCREMENT.

Ändringar:
  recipe.id              → INTEGER PRIMARY KEY AUTOINCREMENT
  recipe.title           → NOT NULL CHECK (trimmad icke-tom)
  ingredient.id          → INTEGER PRIMARY KEY AUTOINCREMENT
  ingredient.name        → NOT NULL, UNIQUE INDEX COLLATE NOCASE
  ingredient.kitchen_staple → NOT NULL DEFAULT 0 CHECK (0/1)
  ingredient.notes       → TEXT (var REAL pga CSV-affinity)
  recipe_ingredient      → får surrogate id PRIMARY KEY (NOT composite),
                           recipe_id + ingredient_id NOT NULL FK,
                           amount REAL (var INTEGER med TEXT-värden),
                           note TEXT (var REAL).
  recipe_with_ingredients → recreated as VIEW på de nya tabellerna.

Datatransform inför schemat:
  amount='efter smak' (6 rader) → amount=NULL, "efter smak" prependeras
                                   till note.
  amount=''           (3 rader) → amount=NULL.

Foreign keys ENFORCED med PRAGMA foreign_keys=ON efter migrationen.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def is_already_hardened(conn: sqlite3.Connection) -> bool:
    sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='recipe'"
    ).fetchone()
    return bool(sql and "INTEGER PRIMARY KEY AUTOINCREMENT" in sql[0])


def counts(conn: sqlite3.Connection) -> dict:
    c = conn.cursor()
    return {
        "recipe": c.execute("SELECT COUNT(*) FROM recipe").fetchone()[0],
        "ingredient": c.execute("SELECT COUNT(*) FROM ingredient").fetchone()[0],
        "recipe_ingredient": c.execute(
            "SELECT COUNT(*) FROM recipe_ingredient"
        ).fetchone()[0],
        "recipe_version": c.execute(
            "SELECT COUNT(*) FROM recipe_version"
        ).fetchone()[0],
    }


def harden(conn: sqlite3.Connection) -> None:
    # FKs OFF during swap so recipe_version's FK to recipe(id) doesn't
    # block the drop/rename dance.
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN")

    # Drop dependent view first (we rebuild it at the end).
    conn.execute("DROP VIEW IF EXISTS recipe_with_ingredients")

    # 0) Pre-cleanup: blank/NULL ingredient.name rows. Refuse if any are
    #    still referenced — that'd indicate 002 missed something.
    blank_referenced = conn.execute("""
        SELECT COUNT(*) FROM recipe_ingredient
        WHERE ingredient_id IN (
            SELECT id FROM ingredient
            WHERE name IS NULL OR TRIM(name) = ''
        )
    """).fetchone()[0]
    if blank_referenced:
        raise RuntimeError(
            f"{blank_referenced} recipe_ingredient rows reference blank-name "
            "ingredients — run 002 again or investigate."
        )
    conn.execute(
        "DELETE FROM ingredient WHERE name IS NULL OR TRIM(name) = ''"
    )

    # 1) Normalize amount text-values before column type change.
    #    'efter smak' → NULL, prepend marker to note.
    conn.execute("""
        UPDATE recipe_ingredient
        SET note = TRIM(
                'efter smak' ||
                CASE WHEN COALESCE(TRIM(note), '') = '' THEN '' ELSE '; ' || note END
            ),
            amount = NULL
        WHERE TRIM(COALESCE(CAST(amount AS TEXT), '')) = 'efter smak'
    """)
    #    '' or whitespace → NULL.
    conn.execute("""
        UPDATE recipe_ingredient
        SET amount = NULL
        WHERE typeof(amount) = 'text' AND TRIM(amount) = ''
    """)

    # 2) New tables.
    conn.execute("""
        CREATE TABLE recipe_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL CHECK (length(TRIM(title)) > 0),
            description TEXT,
            instructions TEXT,
            notes TEXT,
            image_url TEXT,
            tags TEXT,
            section TEXT,
            menu TEXT
        )
    """)
    conn.execute("""
        INSERT INTO recipe_new (id, title, description, instructions, notes,
                                image_url, tags, section, menu)
        SELECT id, title, description, instructions, notes,
               image_url, tags, section, menu
        FROM recipe
    """)

    conn.execute("""
        CREATE TABLE ingredient_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL CHECK (length(TRIM(name)) > 0),
            grocery_category TEXT,
            notes TEXT,
            kitchen_staple INTEGER NOT NULL DEFAULT 0
                CHECK (kitchen_staple IN (0, 1))
        )
    """)
    conn.execute("""
        INSERT INTO ingredient_new (id, name, grocery_category, notes, kitchen_staple)
        SELECT id, name, grocery_category,
               CASE WHEN typeof(notes)='text' THEN notes ELSE NULL END,
               COALESCE(kitchen_staple, 0)
        FROM ingredient
    """)

    conn.execute("""
        CREATE TABLE recipe_ingredient_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL
                REFERENCES recipe(id) ON DELETE CASCADE,
            ingredient_id INTEGER NOT NULL
                REFERENCES ingredient(id) ON DELETE RESTRICT,
            amount REAL,
            unit TEXT,
            note TEXT
        )
    """)
    conn.execute("""
        INSERT INTO recipe_ingredient_new
            (recipe_id, ingredient_id, amount, unit, note)
        SELECT recipe_id, ingredient_id,
               CASE WHEN typeof(amount) IN ('integer','real') THEN amount
                    ELSE NULL END,
               unit,
               CASE WHEN typeof(note)='text' THEN note ELSE NULL END
        FROM recipe_ingredient
    """)

    # 3) Drop old, rename new.
    conn.execute("DROP TABLE recipe_ingredient")
    conn.execute("DROP TABLE ingredient")
    conn.execute("DROP TABLE recipe")
    conn.execute("ALTER TABLE recipe_new RENAME TO recipe")
    conn.execute("ALTER TABLE ingredient_new RENAME TO ingredient")
    conn.execute("ALTER TABLE recipe_ingredient_new RENAME TO recipe_ingredient")

    # 4) Indexes.
    conn.execute(
        "CREATE UNIQUE INDEX idx_ingredient_name "
        "ON ingredient(name COLLATE NOCASE)"
    )
    conn.execute(
        "CREATE INDEX idx_recipe_ingredient_recipe "
        "ON recipe_ingredient(recipe_id)"
    )
    conn.execute(
        "CREATE INDEX idx_recipe_ingredient_ingredient "
        "ON recipe_ingredient(ingredient_id)"
    )
    # idx_recipe_version_recipe survived the migration (we never dropped
    # recipe_version), but recreate defensively in case it was dropped manually.
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_recipe_version_recipe "
        "ON recipe_version(recipe_id, version_number)"
    )

    # 5) Seed sqlite_sequence so AUTOINCREMENT continues past existing ids.
    #    sqlite_sequence has no UNIQUE constraint, so DELETE+INSERT instead
    #    of UPSERT.
    for table in ("recipe", "ingredient", "recipe_ingredient"):
        max_id = conn.execute(
            f"SELECT COALESCE(MAX(id), 0) FROM {table}"
        ).fetchone()[0]
        conn.execute("DELETE FROM sqlite_sequence WHERE name = ?", (table,))
        conn.execute(
            "INSERT INTO sqlite_sequence(name, seq) VALUES (?, ?)",
            (table, max_id),
        )

    # 6) Rebuild the convenience VIEW on the new tables.
    conn.execute("""
        CREATE VIEW recipe_with_ingredients AS
        SELECT
            r.id AS recipe_id, r.title, r.description, r.instructions,
            r.notes, r.image_url, r.tags, r.section, r.menu,
            i.id AS ingredient_id, i.name AS ingredient_name,
            i.grocery_category, i.kitchen_staple,
            ri.amount, ri.unit, ri.note AS ingredient_note
        FROM recipe r
        LEFT JOIN recipe_ingredient ri ON ri.recipe_id = r.id
        LEFT JOIN ingredient i ON i.id = ri.ingredient_id
    """)

    conn.execute("COMMIT")
    conn.execute("PRAGMA foreign_keys = ON")

    # 7) Verify FK integrity end-to-end.
    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(f"FK violations after migration: {violations}")


def main() -> int:
    db_path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/recipe.db")
    if not db_path.exists():
        print(f"✗ DB not found: {db_path}", file=sys.stderr)
        return 1

    # sqlite3.connect with isolation_level=None gives us manual transaction control.
    conn = sqlite3.connect(str(db_path), isolation_level=None)

    if is_already_hardened(conn):
        print("✓ Schema already hardened (recipe.id is INTEGER PRIMARY KEY AUTOINCREMENT). No-op.")
        return 0

    before = counts(conn)
    print(f"--- BEFORE ({db_path}) ---")
    for k, v in before.items():
        print(f"  {k}: {v}")

    try:
        harden(conn)
    except Exception as e:
        # If we crashed mid-migration, the transaction auto-rolls back when
        # the connection closes. Re-raise so the operator sees what broke.
        try:
            conn.execute("ROLLBACK")
        except sqlite3.OperationalError:
            pass
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        return 1

    after = counts(conn)
    invariant = ("recipe", "recipe_ingredient", "recipe_version")
    print(f"\n--- AFTER ---")
    for k, v in after.items():
        marker = " ✗ row count changed!" if (k in invariant and before[k] != v) else ""
        print(f"  {k}: {v}{marker}")

    # recipe, recipe_ingredient, recipe_version must be invariant. ingredient
    # may drop by however many blank-name rows the pre-cleanup removed.
    invariant = ("recipe", "recipe_ingredient", "recipe_version")
    if any(before[k] != after[k] for k in invariant):
        print("\n✗ Row counts changed during migration — investigate!", file=sys.stderr)
        return 2
    if before["ingredient"] != after["ingredient"]:
        print(f"\n  (pre-cleanup removed {before['ingredient'] - after['ingredient']} "
              "blank-name ingredient rows)")

    print("\n✓ Schema hardening successful. FK integrity verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
