#!/usr/bin/env python3
"""
Migration 001: Create recipe_version table and backfill version 1 per existing recipe.
Idempotent — safe to run multiple times.
Usage: python3 001_recipe_version.py /path/to/recipe.db
"""
import sqlite3
import json
import sys
from datetime import datetime, timezone

DB_PATH = sys.argv[1] if len(sys.argv) > 1 else 'recipe.db'

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.executescript('''
CREATE TABLE IF NOT EXISTS recipe_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL,
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
    FOREIGN KEY (recipe_id) REFERENCES recipe(id)
);
CREATE INDEX IF NOT EXISTS idx_recipe_version_recipe ON recipe_version(recipe_id, version_number);
''')

recipes = cur.execute("SELECT * FROM recipe").fetchall()
backfilled = 0
for r in recipes:
    exists = cur.execute(
        "SELECT 1 FROM recipe_version WHERE recipe_id=? AND version_number=1", (r['id'],)
    ).fetchone()
    if exists:
        continue

    ings = cur.execute('''
        SELECT i.id AS ingredient_id, i.name, ri.amount, ri.unit, ri.note
        FROM recipe_ingredient ri
        JOIN ingredient i ON ri.ingredient_id = i.id
        WHERE ri.recipe_id = ?
    ''', (r['id'],)).fetchall()
    ingredients_json = json.dumps([dict(row) for row in ings], ensure_ascii=False)

    cur.execute('''
        INSERT INTO recipe_version
            (recipe_id, version_number, title, description, instructions, notes,
             image_url, tags, section, menu, ingredients_json, changed_at, changed_by, change_note)
        VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'migration', 'Initial backfill')
    ''', (
        r['id'], r['title'], r['description'], r['instructions'], r['notes'],
        r['image_url'], r['tags'], r['section'], r['menu'],
        ingredients_json,
        datetime.now(timezone.utc).isoformat(),
    ))
    backfilled += 1

conn.commit()
conn.close()
print(f"Done. Table created/verified. Backfilled {backfilled} recipe(s).")
