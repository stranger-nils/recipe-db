#!/usr/bin/env python3
"""
Apply a pending-commit JSON to the VPS database via SSH.
Usage:
    echo '<json>' | python3 scripts/skill_remote_commit.py
    python3 scripts/skill_remote_commit.py < .claude/pending-commits/file.json
Returns JSON on stdout: {"status": "ok"|"error", "recipe_id": N, "version_number": N, "message": "..."}
"""
import base64
import json
import subprocess
import sys


VPS = 'minvps'
DB_PATH = '/opt/recipe-db/data/recipe.db'


def build_vps_script(commit_b64: str) -> str:
    return f"""import sqlite3, json, base64
from datetime import datetime, timezone

DB = '{DB_PATH}'
commit = json.loads(base64.b64decode('{commit_b64}').decode())
op = commit.get('operation', 'create')

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
cur = conn.cursor()

def read_ings(recipe_id):
    return cur.execute('''
        SELECT i.id AS ingredient_id, i.name, ri.amount, ri.unit, ri.note
        FROM recipe_ingredient ri JOIN ingredient i ON ri.ingredient_id = i.id
        WHERE ri.recipe_id = ?
    ''', (recipe_id,)).fetchall()

def upsert_ingredient(ing):
    name = ing.get('name', '')
    cur.execute(
        "INSERT OR IGNORE INTO ingredient (name, grocery_category, notes, kitchen_staple) VALUES (?, ?, '', ?)",
        (name, ing.get('grocery_category', ''), ing.get('kitchen_staple', 0))
    )
    row = cur.execute("SELECT id FROM ingredient WHERE LOWER(name)=LOWER(?)", (name,)).fetchone()
    return row[0] if row else None

try:
    cur.execute('BEGIN')
    now = datetime.now(timezone.utc).isoformat()

    if op == 'create':
        cur.execute('''
            INSERT INTO recipe (title, description, instructions, notes, image_url, tags, section, menu)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (commit.get('title'), commit.get('description'), commit.get('instructions'),
              commit.get('notes'), commit.get('image_url'), commit.get('tags'),
              commit.get('section'), commit.get('menu')))
        recipe_id = cur.lastrowid

        for ing in commit.get('ingredients', []):
            ing_id = upsert_ingredient(ing)
            if ing_id:
                cur.execute('''
                    INSERT INTO recipe_ingredient (recipe_id, ingredient_id, amount, unit, note)
                    VALUES (?, ?, ?, ?, ?)
                ''', (recipe_id, ing_id, ing.get('amount', ''), ing.get('unit', ''), ing.get('note', '')))

        ings_json = json.dumps([dict(r) for r in read_ings(recipe_id)], ensure_ascii=False)
        cur.execute('''
            INSERT INTO recipe_version (recipe_id, version_number, title, description, instructions,
                notes, image_url, tags, section, menu, ingredients_json, changed_at, changed_by, change_note)
            VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'chat', 'Skapat via chat')
        ''', (recipe_id, commit.get('title'), commit.get('description'), commit.get('instructions'),
              commit.get('notes'), commit.get('image_url'), commit.get('tags'),
              commit.get('section'), commit.get('menu'), ings_json, now))
        version_number = 1

    elif op == 'update':
        recipe_id = commit['recipe_id']
        cur_recipe = cur.execute("SELECT * FROM recipe WHERE id=?", (recipe_id,)).fetchone()
        if not cur_recipe:
            raise ValueError(f"Recipe {{recipe_id}} not found")

        cur_ings = read_ings(recipe_id)
        next_ver = cur.execute(
            "SELECT COALESCE(MAX(version_number),0)+1 FROM recipe_version WHERE recipe_id=?", (recipe_id,)
        ).fetchone()[0]

        cur.execute('''
            INSERT INTO recipe_version (recipe_id, version_number, title, description, instructions,
                notes, image_url, tags, section, menu, ingredients_json, changed_at, changed_by, change_note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'chat', ?)
        ''', (recipe_id, next_ver,
              cur_recipe['title'], cur_recipe['description'], cur_recipe['instructions'],
              cur_recipe['notes'], cur_recipe['image_url'], cur_recipe['tags'],
              cur_recipe['section'], cur_recipe['menu'],
              json.dumps([dict(r) for r in cur_ings], ensure_ascii=False),
              now, commit.get('change_note', 'Uppdaterat via chat')))
        version_number = next_ver

        cur.execute('''
            UPDATE recipe SET title=?, description=?, instructions=?, notes=?,
                image_url=?, tags=?, section=?, menu=? WHERE id=?
        ''', (
            commit.get('title', cur_recipe['title']),
            commit.get('description', cur_recipe['description']),
            commit.get('instructions', cur_recipe['instructions']),
            commit.get('notes', cur_recipe['notes']),
            commit.get('image_url', cur_recipe['image_url']),
            commit.get('tags', cur_recipe['tags']),
            commit.get('section', cur_recipe['section']),
            commit.get('menu', cur_recipe['menu']),
            recipe_id
        ))

        if 'ingredients' in commit:
            cur.execute("DELETE FROM recipe_ingredient WHERE recipe_id=?", (recipe_id,))
            for ing in commit['ingredients']:
                ing_id = upsert_ingredient(ing)
                if ing_id:
                    cur.execute('''
                        INSERT INTO recipe_ingredient (recipe_id, ingredient_id, amount, unit, note)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (recipe_id, ing_id, ing.get('amount', ''), ing.get('unit', ''), ing.get('note', '')))
    else:
        raise ValueError(f"Unknown operation: {{op}}")

    conn.commit()
    print(json.dumps({{"status": "ok", "recipe_id": recipe_id, "version_number": version_number}}))

except Exception as e:
    try:
        conn.rollback()
    except Exception:
        pass
    print(json.dumps({{"status": "error", "message": str(e)}}))
finally:
    conn.close()
"""


def main():
    raw = sys.stdin.read().strip()
    if not raw:
        print(json.dumps({"status": "error", "message": "No input on stdin"}))
        sys.exit(1)
    try:
        json.loads(raw)
    except json.JSONDecodeError as e:
        print(json.dumps({"status": "error", "message": f"Invalid JSON: {e}"}))
        sys.exit(1)

    commit_b64 = base64.b64encode(raw.encode()).decode()
    vps_script = build_vps_script(commit_b64)

    result = subprocess.run(
        ['ssh', VPS, 'python3', '-'],
        input=vps_script.encode(),
        capture_output=True,
    )
    stdout = result.stdout.decode().strip()
    stderr = result.stderr.decode().strip()

    if result.returncode != 0:
        print(json.dumps({"status": "error", "message": stderr or "SSH failed"}))
        sys.exit(1)

    # The last line of stdout should be the JSON result
    for line in reversed(stdout.splitlines()):
        line = line.strip()
        if line.startswith('{'):
            print(line)
            parsed = json.loads(line)
            sys.exit(0 if parsed.get('status') == 'ok' else 1)

    print(json.dumps({"status": "error", "message": f"Unexpected output: {stdout}"}))
    sys.exit(1)


if __name__ == '__main__':
    main()
