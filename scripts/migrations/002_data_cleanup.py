#!/usr/bin/env python3
"""
Fas A — datastädning före schema-härdning (003).

Idempotent. Body körs inom EN transaktion — antingen lyckas allt eller inget
ändras. Tar DB-path som arg (default: data/recipe.db).

Steg:
  1. Återställ ingredient.id = rowid för NULL-id-rader (löser 9 orphan
     recipe_ingredient-rader på recipe 20).
  2. Merga 16 case-insensitive ingredient-namnsdubletter till lägsta id;
     omdirigera recipe_ingredient.ingredient_id; radera dubblett-raderna.
  3. Konvertera recipe_with_ingredients från legacy-tabell till VIEW.

Verifierar pre- och post-conditions och printar diff.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


def counts(conn: sqlite3.Connection) -> dict:
    c = conn.cursor()
    return {
        "recipe": c.execute("SELECT COUNT(*) FROM recipe").fetchone()[0],
        "ingredient": c.execute("SELECT COUNT(*) FROM ingredient").fetchone()[0],
        "recipe_ingredient": c.execute(
            "SELECT COUNT(*) FROM recipe_ingredient"
        ).fetchone()[0],
        "null_ingredient_id": c.execute(
            "SELECT COUNT(*) FROM ingredient WHERE id IS NULL"
        ).fetchone()[0],
        "orphan_recipe_ingredient": c.execute(
            "SELECT COUNT(*) FROM recipe_ingredient ri "
            "LEFT JOIN ingredient i ON ri.ingredient_id = i.id "
            "WHERE i.id IS NULL"
        ).fetchone()[0],
        "duplicate_ingredient_groups": c.execute(
            "SELECT COUNT(*) FROM (SELECT LOWER(name) FROM ingredient "
            "GROUP BY LOWER(name) HAVING COUNT(*) > 1)"
        ).fetchone()[0],
    }


def fix_null_ingredient_ids(conn: sqlite3.Connection) -> int:
    """Step 1: ingredient.id = rowid where id IS NULL."""
    cur = conn.execute("UPDATE ingredient SET id = rowid WHERE id IS NULL")
    return cur.rowcount


def merge_duplicate_ingredients(conn: sqlite3.Connection) -> tuple[int, int]:
    """Step 2: merge case-insensitive name duplicates to canonical (lowest) id.

    Returns (groups_merged, rows_deleted)."""
    groups = conn.execute(
        "SELECT LOWER(name) AS lname, MIN(id) AS canonical "
        "FROM ingredient GROUP BY LOWER(name) HAVING COUNT(*) > 1"
    ).fetchall()

    groups_merged = 0
    rows_deleted = 0
    for lname, canonical in groups:
        # Find all ids in this group (case-insensitive match), excluding canonical.
        dupe_ids = [
            row[0] for row in conn.execute(
                "SELECT id FROM ingredient WHERE LOWER(name) = ? AND id != ?",
                (lname, canonical),
            ).fetchall()
        ]
        if not dupe_ids:
            continue
        placeholders = ",".join("?" * len(dupe_ids))
        # Repoint recipe_ingredient FKs to canonical id.
        conn.execute(
            f"UPDATE recipe_ingredient SET ingredient_id = ? "
            f"WHERE ingredient_id IN ({placeholders})",
            [canonical, *dupe_ids],
        )
        # Delete duplicate ingredient rows.
        cur = conn.execute(
            f"DELETE FROM ingredient WHERE id IN ({placeholders})",
            dupe_ids,
        )
        rows_deleted += cur.rowcount
        groups_merged += 1
    return groups_merged, rows_deleted


def replace_recipe_with_ingredients_view(conn: sqlite3.Connection) -> None:
    """Step 3: drop legacy table, recreate as live VIEW."""
    # Detect whether the existing object is a table or a view, then drop
    # with the matching statement (SQLite errors if you mix them up).
    obj = conn.execute(
        "SELECT type FROM sqlite_master WHERE name = 'recipe_with_ingredients'"
    ).fetchone()
    if obj and obj[0] == "table":
        conn.execute("DROP TABLE recipe_with_ingredients")
    elif obj and obj[0] == "view":
        conn.execute("DROP VIEW recipe_with_ingredients")
    conn.execute("""
        CREATE VIEW recipe_with_ingredients AS
        SELECT
            r.id           AS recipe_id,
            r.title        AS title,
            r.description  AS description,
            r.instructions AS instructions,
            r.notes        AS notes,
            r.image_url    AS image_url,
            r.tags         AS tags,
            r.section      AS section,
            r.menu         AS menu,
            i.id           AS ingredient_id,
            i.name         AS ingredient_name,
            i.grocery_category,
            i.kitchen_staple,
            ri.amount,
            ri.unit,
            ri.note        AS ingredient_note
        FROM recipe r
        LEFT JOIN recipe_ingredient ri ON ri.recipe_id = r.id
        LEFT JOIN ingredient i ON i.id = ri.ingredient_id
    """)


def main() -> int:
    db_path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/recipe.db")
    if not db_path.exists():
        print(f"✗ DB not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA foreign_keys = ON")

    before = counts(conn)
    print(f"--- BEFORE ({db_path}) ---")
    for k, v in before.items():
        print(f"  {k}: {v}")

    try:
        conn.execute("BEGIN")
        fixed_ids = fix_null_ingredient_ids(conn)
        groups, deleted = merge_duplicate_ingredients(conn)
        replace_recipe_with_ingredients_view(conn)
        conn.execute("COMMIT")
    except Exception as e:
        conn.execute("ROLLBACK")
        print(f"✗ Migration failed, rolled back: {e}", file=sys.stderr)
        return 1

    after = counts(conn)
    print(f"\n--- ACTIONS ---")
    print(f"  fixed NULL ingredient.id rows: {fixed_ids}")
    print(f"  merged duplicate name groups:  {groups}")
    print(f"  deleted duplicate ing rows:    {deleted}")
    print(f"  recreated recipe_with_ingredients as VIEW")

    print(f"\n--- AFTER ---")
    for k, v in after.items():
        marker = " ✗" if k in ("null_ingredient_id", "orphan_recipe_ingredient",
                               "duplicate_ingredient_groups") and v != 0 else ""
        print(f"  {k}: {v}{marker}")

    bad = (after["null_ingredient_id"] + after["orphan_recipe_ingredient"]
           + after["duplicate_ingredient_groups"])
    if bad != 0:
        print("\n✗ Post-conditions not met — investigate.", file=sys.stderr)
        return 2
    print("\n✓ Data cleanup successful.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
