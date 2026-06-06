#!/usr/bin/env python3
"""
Migration 007 — recipe_annotation: minnesanteckningar per version.

En annotation hör till en specifik version av ett recept och pekar antingen på
en ingrediens (target_type='ingredient', target_key=ingrediensnamn) eller ett
steg (target_type='step', target_key=stegindex som textsträng).

Idempotent: bail:ar om tabellen redan finns.
"""
from __future__ import annotations
import os
import sys
import sqlite3

DB_PATH = os.environ.get("DB_PATH", "recipe.db")


def main() -> int:
    if not os.path.exists(DB_PATH):
        print(f"DB saknas: {DB_PATH}", file=sys.stderr)
        return 1
    con = sqlite3.connect(DB_PATH)
    try:
        cur = con.cursor()
        existing = cur.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='recipe_annotation'"
        ).fetchone()
        if existing:
            print("recipe_annotation finns redan — hoppar över.")
            return 0
        cur.executescript(
            """
            CREATE TABLE recipe_annotation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                recipe_id INTEGER NOT NULL REFERENCES recipe(id) ON DELETE CASCADE,
                version_number INTEGER NOT NULL,
                target_type TEXT NOT NULL CHECK (target_type IN ('ingredient','step')),
                target_key TEXT NOT NULL,
                text TEXT NOT NULL CHECK (length(TRIM(text)) > 0),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                UNIQUE (recipe_id, version_number, target_type, target_key)
            );
            CREATE INDEX idx_recipe_annotation_recipe
                ON recipe_annotation(recipe_id, version_number);
            """
        )
        con.commit()
        print("recipe_annotation skapad.")
        return 0
    finally:
        con.close()


if __name__ == "__main__":
    sys.exit(main())
