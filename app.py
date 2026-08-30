from dotenv import load_dotenv
import os
import json
import difflib
import hmac
import subprocess
import sys
from datetime import datetime, timezone
from flask import Flask, request, render_template, redirect, url_for, jsonify
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

load_dotenv()

app = Flask(__name__)


# Database configuration — plain SQLite.
# Local dev: defaults to sqlite:///recipe.db.
# VPS: DATABASE_URL is set via docker-compose to sqlite:///recipe.db
#      and bind-mounted from /opt/recipe-db/data/recipe.db on the host.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///recipe.db")
engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)


def _backup_before_edit(note: str | None = None) -> None:
    """Take a pre-edit SQLite snapshot if BACKUP_DIR is configured.
    No-op on local dev (BACKUP_DIR unset). Failures are logged but never
    block the edit — backups are defense-in-depth, recipe_version is the
    authoritative per-row history."""
    if not os.environ.get("BACKUP_DIR"):
        return
    script = os.path.join(os.path.dirname(__file__), "scripts", "backup_db.py")
    cmd = [sys.executable, script, "pre-edit"]
    if note:
        cmd.append(f"--note={note}")
    try:
        subprocess.run(cmd, check=True, timeout=30, capture_output=True)
    except Exception as e:  # noqa: BLE001 — never let backup failure break edits
        print(f"backup_before_edit failed: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Recipe edit helper — shared by the web form and the JSON API.
# ---------------------------------------------------------------------------

class RecipeNotFound(Exception):
    pass


class VersionConflict(Exception):
    def __init__(self, current_version, expected_version):
        self.current_version = current_version
        self.expected_version = expected_version
        super().__init__(
            f"Version conflict: expected {expected_version}, current is {current_version}"
        )


class IngredientNotInCatalog(Exception):
    """Raised when an ingredient name doesn't resolve to the canonical catalog
    and the caller hasn't supplied enough metadata (grocery_category + default_unit)
    to create a new canonical row."""
    def __init__(self, name, missing):
        self.name = name
        self.missing = missing
        super().__init__(
            f"Ingrediensen '{name}' finns inte i katalogen. "
            f"Lägg till den via /ingredient_library, eller skicka {missing} "
            f"med skrivningen. Använd existerande namn eller alias."
        )


ALLOWED_GROCERY_CATEGORIES = {
    "Frukt och grönt", "Färska örter", "Mejeri", "Kött", "Fågel", "Fläsk",
    "Fisk", "Kolhydrater", "Baljväxter", "Konserver", "Smaksättare",
    "Färdiga tillbehör", "Bageri", "Frys", "Alkohol", "Övrigt",
}


def _resolve_ingredient_id(conn, name):
    """Return canonical ingredient id for `name`, matching by name (NOCASE)
    or by aliases JSON-array. Returns None if no match in the catalog."""
    name = (name or '').strip()
    if not name:
        return None
    row_id = conn.execute(
        text("SELECT id FROM ingredient WHERE name = :name COLLATE NOCASE"),
        {'name': name},
    ).scalar()
    if row_id:
        return row_id
    # Alias lookup. aliases is a JSON array of strings stored per ingredient.
    rows = conn.execute(text("SELECT id, aliases FROM ingredient")).mappings().all()
    target = name.lower()
    for r in rows:
        try:
            aliases = json.loads(r['aliases'] or '[]')
        except (TypeError, ValueError):
            continue
        if any(target == (a or '').strip().lower() for a in aliases):
            return r['id']
    return None


def _resolve_or_create_ingredient(conn, name, grocery_category=None,
                                  default_unit=None, kitchen_staple=0):
    """Strict resolver: matches the canonical catalog by name or alias.
    Only creates a new row if BOTH grocery_category (valid) and default_unit
    are supplied — otherwise raises IngredientNotInCatalog so the caller can
    surface a helpful error rather than silently fabricating a NULL-category
    entry."""
    name = (name or '').strip()
    if not name:
        return None
    existing = _resolve_ingredient_id(conn, name)
    if existing:
        return existing

    missing = []
    if not grocery_category or grocery_category not in ALLOWED_GROCERY_CATEGORIES:
        missing.append('grocery_category')
    if not default_unit or not str(default_unit).strip():
        missing.append('default_unit')
    if missing:
        raise IngredientNotInCatalog(name, missing)

    conn.execute(
        text(
            "INSERT INTO ingredient (name, grocery_category, default_unit, "
            "                        kitchen_staple, aliases) "
            "VALUES (:name, :gc, :du, :ks, '[]')"
        ),
        {
            'name': name,
            'gc': grocery_category,
            'du': str(default_unit).strip(),
            'ks': 1 if kitchen_staple else 0,
        },
    )
    return conn.execute(
        text("SELECT id FROM ingredient WHERE name = :name COLLATE NOCASE"),
        {'name': name},
    ).scalar()


def apply_recipe_edit(conn, recipe_id, new_state, change_note=None,
                      changed_by='chat', expected_version=None):
    """
    Update an existing recipe with versioning.

    new_state keys (all optional — missing keys keep the current value):
        title, description, instructions, notes, tags, type, kitchen
        ingredients: list of dicts {name, amount, unit, note,
                                    grocery_category, kitchen_staple}.
                     If omitted/None, existing ingredients are kept untouched.
                     If provided, ingredients are fully replaced.
    """
    cur_recipe = conn.execute(
        text("SELECT * FROM recipe WHERE id=:id"), {'id': recipe_id}
    ).mappings().first()
    if not cur_recipe:
        raise RecipeNotFound(f"Recipe {recipe_id} not found")

    cur_ings = conn.execute(text('''
        SELECT i.id AS ingredient_id, i.name, ri.amount, ri.unit, ri.note
        FROM recipe_ingredient ri
        JOIN ingredient i ON ri.ingredient_id = i.id
        WHERE ri.recipe_id = :id
    '''), {'id': recipe_id}).mappings().all()

    current_version = conn.execute(
        text("SELECT COALESCE(MAX(version_number),0) FROM recipe_version WHERE recipe_id=:id"),
        {'id': recipe_id},
    ).scalar() or 0

    if expected_version is not None and int(expected_version) != int(current_version):
        raise VersionConflict(current_version, expected_version)

    next_ver = current_version + 1
    now = datetime.now(timezone.utc).isoformat()

    # 1. Snapshot the pre-edit state.
    conn.execute(text('''
        INSERT INTO recipe_version
            (recipe_id, version_number, title, description, instructions, notes,
             tags, type, kitchen, ingredients_json, changed_at,
             changed_by, change_note)
        VALUES (:recipe_id, :ver, :title, :description, :instructions, :notes,
                :tags, :type, :kitchen, :ings_json, :changed_at,
                :changed_by, :change_note)
    '''), {
        'recipe_id': recipe_id, 'ver': next_ver,
        'title': cur_recipe['title'], 'description': cur_recipe['description'],
        'instructions': cur_recipe['instructions'], 'notes': cur_recipe['notes'],
        'tags': cur_recipe['tags'],
        'type': cur_recipe['type'], 'kitchen': cur_recipe['kitchen'],
        'ings_json': json.dumps([dict(r) for r in cur_ings], ensure_ascii=False),
        'changed_at': now, 'changed_by': changed_by, 'change_note': change_note,
    })

    # 1b. Re-anchor any cook-log entry on the live state (version 0) to the
    #     snapshot we just froze. The content the user cooked/evaluated now lives
    #     at recipe_version.next_ver, so its tillagningsstatus must follow it.
    #     The new live state (version 0) is thereby left unproven again.
    try:
        conn.execute(text('''
            UPDATE cook_log SET version_number=:next_ver, updated_at=:now
            WHERE recipe_id=:rid AND version_number=0
        '''), {'next_ver': next_ver, 'now': now, 'rid': recipe_id})
    except Exception:
        # cook_log saknas (migration 008 ej körd) — edit ska inte blockeras.
        pass

    # 2. UPDATE the recipe row (preserve current value for fields not in new_state).
    conn.execute(text('''
        UPDATE recipe SET
            title=:title, description=:description, instructions=:instructions,
            notes=:notes, tags=:tags, type=:type, kitchen=:kitchen
        WHERE id=:id
    '''), {
        'title': new_state.get('title', cur_recipe['title']),
        'description': new_state.get('description', cur_recipe['description']),
        'instructions': new_state.get('instructions', cur_recipe['instructions']),
        'notes': new_state.get('notes', cur_recipe['notes']),
        'tags': new_state.get('tags', cur_recipe['tags']),
        'type': new_state.get('type', cur_recipe['type']),
        'kitchen': new_state.get('kitchen', cur_recipe['kitchen']),
        'id': recipe_id,
    })

    # 3. Replace ingredient links if a new list was provided.
    if 'ingredients' in new_state and new_state['ingredients'] is not None:
        conn.execute(text("DELETE FROM recipe_ingredient WHERE recipe_id=:id"),
                     {'id': recipe_id})
        for ing in new_state['ingredients']:
            ing_id = _resolve_or_create_ingredient(
                conn,
                name=ing.get('name', ''),
                grocery_category=ing.get('grocery_category'),
                default_unit=ing.get('default_unit'),
                kitchen_staple=ing.get('kitchen_staple', 0),
            )
            if not ing_id:
                continue
            conn.execute(text('''
                INSERT INTO recipe_ingredient (recipe_id, ingredient_id, amount, unit, note)
                VALUES (:recipe_id, :ingredient_id, :amount, :unit, :note)
            '''), {
                'recipe_id': recipe_id,
                'ingredient_id': ing_id,
                'amount': str(ing.get('amount', '') or ''),
                'unit': ing.get('unit', '') or '',
                'note': ing.get('note', '') or '',
            })

    return {
        'recipe_id': recipe_id,
        'new_version_number': next_ver,
        'changed_at': now,
    }


def create_recipe(conn, new_state, changed_by='chat'):
    """Create a brand-new recipe together with its initial version (version 1).

    new_state keys:
        title (required), description, instructions, notes, tags, type, kitchen
        ingredients: list of dicts {name, amount, unit, note,
                                    grocery_category, default_unit, kitchen_staple}.
                     New ingredients are created only when grocery_category +
                     default_unit are supplied; otherwise IngredientNotInCatalog
                     is raised — same contract as apply_recipe_edit, so the caller
                     can surface a helpful error instead of fabricating NULL rows.
    Returns {recipe_id, new_version_number, changed_at}.
    """
    now = datetime.now(timezone.utc).isoformat()

    fields = {
        'title': (new_state.get('title') or '').strip(),
        'description': new_state.get('description') or '',
        'instructions': new_state.get('instructions') or '',
        'notes': new_state.get('notes') or '',
        'kitchen': new_state.get('kitchen') or '',
        'type': new_state.get('type') or '',
        'tags': new_state.get('tags') or '',
    }

    res = conn.execute(text('''
        INSERT INTO recipe (title, description, instructions, notes, kitchen, type, tags)
        VALUES (:title, :description, :instructions, :notes, :kitchen, :type, :tags)
    '''), fields)
    recipe_id = res.lastrowid

    for ing in (new_state.get('ingredients') or []):
        ing_id = _resolve_or_create_ingredient(
            conn,
            name=ing.get('name', ''),
            grocery_category=ing.get('grocery_category'),
            default_unit=ing.get('default_unit'),
            kitchen_staple=ing.get('kitchen_staple', 0),
        )
        if not ing_id:
            continue
        conn.execute(text('''
            INSERT INTO recipe_ingredient (recipe_id, ingredient_id, amount, unit, note)
            VALUES (:recipe_id, :ingredient_id, :amount, :unit, :note)
        '''), {
            'recipe_id': recipe_id,
            'ingredient_id': ing_id,
            'amount': str(ing.get('amount', '') or ''),
            'unit': ing.get('unit', '') or '',
            'note': ing.get('note', '') or '',
        })

    new_ings = conn.execute(text('''
        SELECT i.id AS ingredient_id, i.name, ri.amount, ri.unit, ri.note
        FROM recipe_ingredient ri
        JOIN ingredient i ON ri.ingredient_id = i.id
        WHERE ri.recipe_id = :id
    '''), {'id': recipe_id}).mappings().all()

    conn.execute(text('''
        INSERT INTO recipe_version
            (recipe_id, version_number, title, description, instructions, notes,
             tags, type, kitchen, ingredients_json, changed_at, changed_by, change_note)
        VALUES (:recipe_id, 1, :title, :description, :instructions, :notes,
                :tags, :type, :kitchen, :ings_json, :changed_at, :changed_by, 'Initial version')
    '''), {
        'recipe_id': recipe_id,
        **fields,
        'ings_json': json.dumps([dict(r) for r in new_ings], ensure_ascii=False),
        'changed_at': now,
        'changed_by': changed_by,
    })

    return {
        'recipe_id': recipe_id,
        'new_version_number': 1,
        'changed_at': now,
    }


# ---------------------------------------------------------------------------
# JSON API auth — bearer token via the RECIPE_API_TOKEN env var.
# ---------------------------------------------------------------------------

def _check_api_token():
    """Return None if authorized, else a (response, status) tuple."""
    expected = os.getenv("RECIPE_API_TOKEN", "")
    if not expected:
        return jsonify({'error': 'API disabled (RECIPE_API_TOKEN not set on server)'}), 503
    auth = request.headers.get('Authorization', '')
    if not auth.startswith('Bearer '):
        return jsonify({'error': 'Missing bearer token'}), 401
    provided = auth[len('Bearer '):].strip()
    if not hmac.compare_digest(provided, expected):
        return jsonify({'error': 'Invalid bearer token'}), 401
    return None


default_sql_query = (
    "SELECT DISTINCT\n"
    "    recipe_id,\n"
    "    title,\n"
    "    description,\n"
    "    instructions,\n"
    "    notes,\n"
    "    tags\n"
    "FROM recipe_with_ingredients\n"
    "WHERE 1=1\n"
    "    -- AND ingredient_name = ...\n"
)

GROUP_BY_OPTIONS = {'none', 'kitchen', 'type'}


# ---------------------------------------------------------------------------
# Recept-IDE — shell + view selectors.
# ---------------------------------------------------------------------------

def _parse_steps(instructions):
    """Split free-form instruction text into discrete steps.
    Handles double-newline blocks first (preferred), falls back to single lines.
    Strips a leading '<n>. ' or '<n>) ' enumeration marker."""
    import re
    if not instructions:
        return []
    raw = instructions.strip()
    blocks = [b.strip() for b in re.split(r'\n\s*\n', raw) if b.strip()]
    if len(blocks) <= 1:
        blocks = [ln.strip() for ln in raw.split('\n') if ln.strip()]
    cleaned = []
    for b in blocks:
        cleaned.append(re.sub(r'^\s*\d+[.)\]]\s+', '', b))
    return cleaned


def _ide_data(mode):
    """Build the data blob embedded in ide.html for client-side rendering
    of the explorer/palette/planning. Kept lean — only fields the JS needs."""
    with engine.connect() as conn:
        recipe_rows = conn.execute(text('''
            SELECT r.id, r.title, r.kitchen, r.type,
                   COALESCE((SELECT MAX(version_number) FROM recipe_version v WHERE v.recipe_id=r.id), 0) AS version_count,
                   (SELECT cl.status FROM cook_log cl WHERE cl.recipe_id=r.id AND cl.version_number=0) AS cook_status
            FROM recipe r ORDER BY r.title
        ''')).mappings().all()
        catalog = conn.execute(text(
            'SELECT id, name, grocery_category FROM ingredient ORDER BY name'
        )).mappings().all()
    return {
        'mode': mode,
        'recipes': [dict(r) for r in recipe_rows],
        'catalog': [dict(c) for c in catalog],
    }


def _ide_render(mode, **kwargs):
    data = _ide_data(mode)
    return render_template(
        'ide.html', mode=mode, data_json=json.dumps(data, ensure_ascii=False),
        **kwargs,
    )


@app.route('/')
def ide_home():
    return _ide_render('recept')


@app.route('/ingredients', methods=['GET', 'POST'])
@app.route('/ingredient_library', methods=['GET', 'POST'])
def ingredient_library():
    with engine.begin() as conn:
        if request.method == 'POST':
            ingredient_ids = [
                row['id'] for row in conn.execute(text(
                    'SELECT id FROM ingredient'
                )).mappings().all()
            ]
            for ing_id in ingredient_ids:
                grocery_category = request.form.get(f'grocery_category_{ing_id}', '').strip()
                default_unit = request.form.get(f'default_unit_{ing_id}', '').strip()
                aliases_raw = request.form.get(f'aliases_{ing_id}', '').strip()
                kitchen_staple = 1 if request.form.get(f'kitchen_staple_{ing_id}') == 'on' else 0
                if grocery_category not in ALLOWED_GROCERY_CATEGORIES:
                    continue
                if not default_unit:
                    continue
                aliases_list = [a.strip() for a in aliases_raw.split(',') if a.strip()]
                conn.execute(
                    text('UPDATE ingredient SET grocery_category=:gc, '
                         'default_unit=:du, kitchen_staple=:ks, aliases=:al '
                         'WHERE id=:id'),
                    {'gc': grocery_category, 'du': default_unit,
                     'ks': kitchen_staple,
                     'al': json.dumps(aliases_list, ensure_ascii=False),
                     'id': ing_id}
                )
            return redirect(url_for('ingredient_library'))

        ingredients = conn.execute(text(
            'SELECT * FROM ingredient ORDER BY name COLLATE NOCASE'
        )).mappings().all()

        ingredient_recipes = {}
        ingredient_aliases = {}
        for ing in ingredients:
            recipe_rows = conn.execute(text(
                'SELECT r.id, r.title FROM recipe r '
                'JOIN recipe_ingredient ri ON ri.recipe_id = r.id '
                'WHERE ri.ingredient_id=:id ORDER BY r.title'
            ), {'id': ing['id']}).mappings().all()
            ingredient_recipes[ing['id']] = [dict(r) for r in recipe_rows]
            try:
                aliases = json.loads(ing['aliases'] or '[]')
            except (TypeError, ValueError):
                aliases = []
            ingredient_aliases[ing['id']] = ', '.join(aliases)

    return _ide_render(
        'ingredienser',
        ingredients=ingredients,
        ingredient_recipes=ingredient_recipes,
        ingredient_aliases=ingredient_aliases,
        allowed_categories=sorted(ALLOWED_GROCERY_CATEGORIES),
    )


@app.route('/plan', methods=['GET'])
@app.route('/shopping-list', methods=['GET'])
def shopping_list_view():
    return _ide_render('planering')


@app.route('/recipe/<int:recipe_id>')
def recipe_detail(recipe_id):
    # Den gamla recipe_detail-vyn är ersatt av IDE-fliken. Bevarad route
    # som omdirigering så befintliga länkar/bookmarks fortsätter funka.
    return redirect(url_for('ide_home') + f'?open={recipe_id}')


# ---------------------------------------------------------------------------
# Fragment endpoints — server-rendered HTML som JS injicerar i tab-paner.
# ---------------------------------------------------------------------------

def _load_recipe_for_view(conn, recipe_id, version_number=None):
    """Returnera (recipe, ingredients_for_view, steps, versions, active_version,
    version_note, annotations_dict). Om version_number anges hämtas snapshot
    från recipe_version.ingredients_json; annars live från recipe + recipe_ingredient."""
    recipe = conn.execute(text('SELECT * FROM recipe WHERE id=:id'), {'id': recipe_id}).mappings().first()
    if not recipe:
        return None
    versions_rows = conn.execute(text('''
        SELECT version_number, changed_at, change_note FROM recipe_version
        WHERE recipe_id=:id ORDER BY version_number
    '''), {'id': recipe_id}).mappings().all()
    current_version_number = versions_rows[-1]['version_number'] if versions_rows else 0

    # Tillagningsstatus per version (0 = live). map: {version_number: {...}}.
    cook_rows = conn.execute(text('''
        SELECT version_number, status, cooked_at, rating, notes
        FROM cook_log WHERE recipe_id=:id
    '''), {'id': recipe_id}).mappings().all()
    cook_map = {c['version_number']: dict(c) for c in cook_rows}

    versions = [
        {
            'version_number': v['version_number'],
            'changed_at': v['changed_at'] or '',
            'change_note': v['change_note'] or '',
            'is_current': v['version_number'] == current_version_number,
            'cook': cook_map.get(v['version_number']),
        }
        for v in versions_rows
    ]

    version_note = None
    if version_number:
        snap = conn.execute(text('''
            SELECT title, description, instructions, notes, tags, type, kitchen,
                   ingredients_json, change_note
            FROM recipe_version WHERE recipe_id=:rid AND version_number=:v
        '''), {'rid': recipe_id, 'v': version_number}).mappings().first()
        if snap:
            # render the historical snapshot
            recipe_view = dict(recipe)
            recipe_view.update({
                'title': snap['title'], 'description': snap['description'],
                'instructions': snap['instructions'], 'notes': snap['notes'],
                'tags': snap['tags'], 'type': snap['type'], 'kitchen': snap['kitchen'],
            })
            try:
                ing_snap = json.loads(snap['ingredients_json'] or '[]')
            except (TypeError, ValueError):
                ing_snap = []
            # Anrika med grocery_category/kitchen_staple från katalogen
            cat_map = {
                r['name']: (r['grocery_category'], r['kitchen_staple'])
                for r in conn.execute(text(
                    'SELECT name, grocery_category, kitchen_staple FROM ingredient'
                )).mappings().all()
            }
            ingredients = []
            for ing in ing_snap:
                name = ing.get('name', '')
                gc, ks = cat_map.get(name, (None, 0))
                ingredients.append({
                    'name': name,
                    'amount': ing.get('amount', ''),
                    'unit': ing.get('unit', ''),
                    'note': ing.get('note', ''),
                    'grocery_category': gc,
                    'kitchen_staple': ks,
                })
            recipe = recipe_view
            version_note = snap['change_note'] or None
        else:
            version_number = None
    if not version_number:
        ing_rows = conn.execute(text('''
            SELECT i.name, ri.amount, ri.unit, ri.note,
                   i.grocery_category, i.kitchen_staple
            FROM recipe_ingredient ri
            JOIN ingredient i ON ri.ingredient_id = i.id
            WHERE ri.recipe_id = :id
            ORDER BY i.grocery_category, i.name
        '''), {'id': recipe_id}).mappings().all()
        ingredients = [dict(r) for r in ing_rows]

    steps = _parse_steps(recipe['instructions'])

    # annotations
    ann_rows = conn.execute(text('''
        SELECT target_type, target_key, text FROM recipe_annotation
        WHERE recipe_id=:id AND version_number=:v
    '''), {'id': recipe_id, 'v': version_number or 0}).mappings().all()
    annotations = {f"{a['target_type']}:{a['target_key']}": a['text'] for a in ann_rows}

    # Cook-bar gäller den version som visas just nu (0 = live).
    cook_version = version_number or 0

    return {
        'recipe': recipe,
        'ingredients': ingredients,
        'steps': steps,
        'versions': versions,
        'active_version': version_number,
        'version_note': version_note,
        'annotations': annotations,
        'base_servings': 4,
        'cook_version': cook_version,
        'cook': cook_map.get(cook_version),
    }


@app.route('/_frag/recipe/<int:recipe_id>')
def frag_recipe(recipe_id):
    v = request.args.get('v', type=int)
    with engine.connect() as conn:
        data = _load_recipe_for_view(conn, recipe_id, v)
    if not data:
        return "Recipe not found", 404
    return render_template('_fragments/recipe.html', **data)


@app.route('/_frag/recipe/<int:recipe_id>/diff')
def frag_recipe_diff(recipe_id):
    v_from = request.args.get('from', type=int)
    v_to = request.args.get('to', type=int)
    with engine.connect() as conn:
        recipe = conn.execute(text('SELECT id, title FROM recipe WHERE id=:id'), {'id': recipe_id}).mappings().first()
        if not recipe:
            return "Recipe not found", 404
        versions_rows = conn.execute(text('''
            SELECT version_number, changed_at, change_note FROM recipe_version
            WHERE recipe_id=:id ORDER BY version_number
        '''), {'id': recipe_id}).mappings().all()
        nums = [v['version_number'] for v in versions_rows]
        if not nums:
            return "<div class='welcome'><p>Det finns inga sparade versioner än.</p></div>"
        if v_to is None:
            v_to = nums[-1]
        if v_from is None:
            v_from = nums[-2] if len(nums) >= 2 else nums[-1]
        ver_a = conn.execute(text(
            'SELECT * FROM recipe_version WHERE recipe_id=:rid AND version_number=:v'
        ), {'rid': recipe_id, 'v': v_from}).mappings().first()
        ver_b = conn.execute(text(
            'SELECT * FROM recipe_version WHERE recipe_id=:rid AND version_number=:v'
        ), {'rid': recipe_id, 'v': v_to}).mappings().first()

    versions = [{'version_number': v['version_number'], 'changed_at': v['changed_at'] or ''} for v in versions_rows]

    try:
        ings_a_list = json.loads((ver_a or {}).get('ingredients_json') or '[]') if ver_a else []
        ings_b_list = json.loads((ver_b or {}).get('ingredients_json') or '[]') if ver_b else []
    except (TypeError, ValueError):
        ings_a_list, ings_b_list = [], []
    ings_a = {(i.get('name') or '').lower(): i for i in ings_a_list}
    ings_b = {(i.get('name') or '').lower(): i for i in ings_b_list}
    ing_rows = []
    counts = {'add': 0, 'del': 0, 'chg': 0}
    seen = set()
    for ing in ings_a_list:
        k = (ing.get('name') or '').lower()
        seen.add(k)
        if k in ings_b:
            b = ings_b[k]
            if (ing.get('amount') != b.get('amount')
                    or ing.get('unit') != b.get('unit')
                    or (ing.get('note') or '') != (b.get('note') or '')):
                ing_rows.append({'type': 'chg', 'a': ing, 'b': b})
                counts['chg'] += 1
            else:
                ing_rows.append({'type': 'same', 'a': ing, 'b': b})
        else:
            ing_rows.append({'type': 'del', 'a': ing, 'b': None})
            counts['del'] += 1
    for ing in ings_b_list:
        k = (ing.get('name') or '').lower()
        if k not in seen:
            ing_rows.append({'type': 'add', 'a': None, 'b': ing})
            counts['add'] += 1

    steps_a = _parse_steps((ver_a or {}).get('instructions') if ver_a else '')
    steps_b = _parse_steps((ver_b or {}).get('instructions') if ver_b else '')
    step_rows = _lcs_diff(steps_a, steps_b)
    for r in step_rows:
        if r['type'] == 'add':
            counts['add'] += 1
        elif r['type'] == 'del':
            counts['del'] += 1

    return render_template(
        '_fragments/diff.html',
        recipe=recipe, versions=versions, v_from=v_from, v_to=v_to,
        ver_a=ver_a, ver_b=ver_b,
        ing_rows=ing_rows, step_rows=step_rows, counts=counts,
    )


def _lcs_diff(a, b):
    n, m = len(a), len(b)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            if a[i] == b[j]:
                dp[i][j] = dp[i + 1][j + 1] + 1
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])
    out = []
    i = j = 0
    while i < n and j < m:
        if a[i] == b[j]:
            out.append({'type': 'same', 'a': a[i], 'b': b[j]}); i += 1; j += 1
        elif dp[i + 1][j] >= dp[i][j + 1]:
            out.append({'type': 'del', 'a': a[i], 'b': None}); i += 1
        else:
            out.append({'type': 'add', 'a': None, 'b': b[j]}); j += 1
    while i < n:
        out.append({'type': 'del', 'a': a[i], 'b': None}); i += 1
    while j < m:
        out.append({'type': 'add', 'a': None, 'b': b[j]}); j += 1
    return out


# ---------------------------------------------------------------------------
# Annotation + planning APIs (client-side persistence).
# ---------------------------------------------------------------------------

@app.route('/api/annotation', methods=['POST'])
def api_annotation_upsert():
    payload = request.get_json(silent=True) or {}
    try:
        recipe_id = int(payload.get('recipe_id'))
        target_type = payload.get('target_type')
        target_key = payload.get('target_key')
        text_val = (payload.get('text') or '').strip()
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid payload'}), 400
    if target_type not in ('ingredient', 'step') or not target_key:
        return jsonify({'error': 'Invalid target'}), 400
    version = payload.get('version')
    version = int(version) if version is not None else 0
    now = datetime.now(timezone.utc).isoformat()
    with engine.begin() as conn:
        if not text_val:
            conn.execute(text('''
                DELETE FROM recipe_annotation
                WHERE recipe_id=:rid AND version_number=:v
                  AND target_type=:tt AND target_key=:tk
            '''), {'rid': recipe_id, 'v': version, 'tt': target_type, 'tk': target_key})
            return jsonify({'ok': True, 'deleted': True})
        # upsert
        existing = conn.execute(text('''
            SELECT id FROM recipe_annotation
            WHERE recipe_id=:rid AND version_number=:v
              AND target_type=:tt AND target_key=:tk
        '''), {'rid': recipe_id, 'v': version, 'tt': target_type, 'tk': target_key}).scalar()
        if existing:
            conn.execute(text(
                'UPDATE recipe_annotation SET text=:t, updated_at=:u WHERE id=:id'
            ), {'t': text_val, 'u': now, 'id': existing})
        else:
            conn.execute(text('''
                INSERT INTO recipe_annotation
                  (recipe_id, version_number, target_type, target_key, text, created_at, updated_at)
                VALUES (:rid, :v, :tt, :tk, :t, :c, :u)
            '''), {'rid': recipe_id, 'v': version, 'tt': target_type,
                   'tk': target_key, 't': text_val, 'c': now, 'u': now})
    return jsonify({'ok': True})


@app.route('/api/cook-log', methods=['POST'])
def api_cook_log_upsert():
    """Sätt tillagningsstatus för en receptversion (0 = live/aktuell).

    Binärt: en rad i cook_log betyder "lagad & utvärderad", annars oprövad.
    Body: {recipe_id, version, status, rating?, notes?, cooked_at?}.
    status='cooked' → lagad (sätter cooked_at till idag om inget anges);
    status saknas/null/'' → ta bort markeringen. En rad per (recipe_id, version)."""
    payload = request.get_json(silent=True) or {}
    try:
        recipe_id = int(payload.get('recipe_id'))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid recipe_id'}), 400
    version = payload.get('version')
    version = int(version) if version not in (None, '') else 0
    status = (payload.get('status') or '').strip() or None
    if status not in (None, 'cooked'):
        return jsonify({'error': 'Invalid status'}), 400

    rating = payload.get('rating')
    try:
        rating = int(rating) if rating not in (None, '') else None
    except (TypeError, ValueError):
        rating = None
    if rating is not None and not (1 <= rating <= 5):
        return jsonify({'error': 'rating must be 1–5'}), 400
    notes = (payload.get('notes') or '').strip() or None
    now = datetime.now(timezone.utc).isoformat()

    with engine.begin() as conn:
        if status is None:
            conn.execute(text(
                'DELETE FROM cook_log WHERE recipe_id=:rid AND version_number=:v'
            ), {'rid': recipe_id, 'v': version})
            return jsonify({'ok': True, 'deleted': True})

        cooked_at = None
        if status == 'cooked':
            cooked_at = (payload.get('cooked_at') or '').strip() or now[:10]

        existing = conn.execute(text(
            'SELECT id FROM cook_log WHERE recipe_id=:rid AND version_number=:v'
        ), {'rid': recipe_id, 'v': version}).scalar()
        if existing:
            conn.execute(text('''
                UPDATE cook_log SET status=:s, cooked_at=:ca, rating=:r,
                       notes=:n, updated_at=:u WHERE id=:id
            '''), {'s': status, 'ca': cooked_at, 'r': rating, 'n': notes,
                   'u': now, 'id': existing})
        else:
            conn.execute(text('''
                INSERT INTO cook_log
                  (recipe_id, version_number, status, cooked_at, rating, notes,
                   created_at, updated_at)
                VALUES (:rid, :v, :s, :ca, :r, :n, :c, :u)
            '''), {'rid': recipe_id, 'v': version, 's': status, 'ca': cooked_at,
                   'r': rating, 'n': notes, 'c': now, 'u': now})
    return jsonify({'ok': True, 'status': status})


@app.route('/api/cook-log', methods=['GET'])
def api_cook_log_list():
    """Vad har lagats, och när. Används av veckomeny-skillen för att undvika
    att föreslå samma rätter vecka efter vecka.

    Query: ?since=YYYY-MM-DD (valfritt) filtrerar på cooked_at.
    Svar: {results: [{recipe_id, title, version_number, cooked_at, rating}]}
    sorterat senast lagat först. Rader utan cooked_at kommer sist."""
    auth_err = _check_api_token()
    if auth_err is not None:
        return auth_err

    since = (request.args.get('since') or '').strip()
    sql = """
        SELECT c.recipe_id, r.title, c.version_number, c.cooked_at, c.rating
        FROM cook_log c JOIN recipe r ON r.id = c.recipe_id
        WHERE c.status = 'cooked'
    """
    params = {}
    if since:
        sql += " AND c.cooked_at >= :since"
        params['since'] = since
    sql += " ORDER BY c.cooked_at IS NULL, c.cooked_at DESC, r.title"

    with engine.connect() as conn:
        rows = conn.execute(text(sql), params).mappings().all()
    return jsonify({'results': [dict(r) for r in rows]})


@app.route('/api/plan/aggregate', methods=['GET'])
def api_plan_aggregate():
    ids = request.args.getlist('ids', type=int)
    if not ids:
        return jsonify({'groups': []})
    with engine.connect() as conn:
        placeholders = ','.join(f':id{i}' for i in range(len(ids)))
        params = {f'id{i}': v for i, v in enumerate(ids)}
        rows = conn.execute(text(f'''
            SELECT i.name, i.grocery_category, i.kitchen_staple,
                   ri.amount, ri.unit
            FROM recipe_ingredient ri
            JOIN ingredient i ON ri.ingredient_id = i.id
            WHERE ri.recipe_id IN ({placeholders})
        '''), params).mappings().all()

    by_cat = {}
    for r in rows:
        cat = r['grocery_category'] or 'Övrigt'
        key = (r['name'] or '').lower() + '|' + (r['unit'] or '').lower()
        entry = by_cat.setdefault(cat, {}).setdefault(key, {
            'key': key, 'name': r['name'], 'unit': r['unit'] or '',
            'pantry': bool(r['kitchen_staple']), 'amounts': [],
        })
        entry['amounts'].append(r['amount'])

    groups = []
    for cat in sorted(by_cat.keys(), key=lambda s: s.lower()):
        items = []
        for it in by_cat[cat].values():
            nums = []
            non_numeric = []
            for a in it['amounts']:
                try:
                    nums.append(float(str(a).replace(',', '.')))
                except (TypeError, ValueError):
                    if a:
                        non_numeric.append(str(a))
            if not non_numeric and nums:
                total = sum(nums)
                qty_display = str(int(total)) if abs(total - int(total)) < 1e-9 else f'{total:g}'
            elif non_numeric and not nums:
                qty_display = ' + '.join(non_numeric)
            else:
                qty_display = ' + '.join([f'{sum(nums):g}'] + non_numeric) if nums else ' + '.join(non_numeric)
            items.append({
                'key': it['key'], 'name': it['name'], 'unit': it['unit'],
                'qty_display': qty_display, 'pantry': it['pantry'],
            })
        items.sort(key=lambda x: x['name'].lower())
        groups.append({'cat': cat, 'items': items})
    return jsonify({'groups': groups})

def _category_options(conn):
    """Distinct existing values for the categorical fields shown in the edit
    form, used to populate <datalist> autocompletes. Free text is still
    allowed — these are suggestions, not constraints."""
    kitchens = [r[0] for r in conn.execute(text(
        "SELECT DISTINCT kitchen FROM recipe "
        "WHERE kitchen IS NOT NULL AND TRIM(kitchen) != '' "
        "ORDER BY kitchen COLLATE NOCASE"
    )).all()]
    types = [r[0] for r in conn.execute(text(
        "SELECT DISTINCT type FROM recipe "
        "WHERE type IS NOT NULL AND TRIM(type) != '' "
        "ORDER BY type COLLATE NOCASE"
    )).all()]
    raw_tags = [r[0] for r in conn.execute(text(
        "SELECT tags FROM recipe WHERE tags IS NOT NULL AND TRIM(tags) != ''"
    )).all()]
    tag_set = set()
    for raw in raw_tags:
        for t in raw.split(','):
            t = t.strip()
            if t:
                tag_set.add(t)
    tags = sorted(tag_set, key=lambda s: s.lower())
    return {'kitchens': kitchens, 'types': types, 'tags': tags}


def _parse_ingredients_textarea(raw):
    """Parse the legacy 'amount unit name' line-by-line textarea into structured rows."""
    rows = []
    for line in (raw or '').strip().split('\n'):
        parts = line.strip().split(' ', 2)
        if len(parts) == 3:
            amount, unit, name = parts
        elif len(parts) == 2:
            amount, unit = parts
            name = ''
        elif len(parts) == 1 and parts[0]:
            amount, unit, name = parts[0], '', ''
        else:
            continue
        rows.append({'name': name, 'amount': amount, 'unit': unit, 'note': ''})
    return rows


@app.route('/recipe/<int:recipe_id>/edit', methods=['GET', 'POST'])
def edit_recipe(recipe_id):

    with engine.begin() as conn:
        if request.method == 'POST':
            new_state = {
                'title': request.form['title'],
                'description': request.form['description'],
                'instructions': request.form['instructions'],
                'notes': request.form['notes'],
                'kitchen': request.form.get('kitchen', ''),
                'type': request.form.get('type', ''),
                'tags': request.form['tags'],
                'ingredients': _parse_ingredients_textarea(request.form['ingredients']),
            }

            _backup_before_edit(note=f"web-{recipe_id}")
            try:
                apply_recipe_edit(
                    conn, recipe_id, new_state,
                    change_note=None, changed_by='web',
                )
            except RecipeNotFound:
                return "Recipe not found", 404
            except IngredientNotInCatalog as e:
                recipe = conn.execute(
                    text("SELECT * FROM recipe WHERE id=:id"), {'id': recipe_id}
                ).mappings().first()
                return render_template(
                    'edit_recipe.html',
                    recipe=recipe,
                    ingredients_text=request.form['ingredients'],
                    is_new=False,
                    error=str(e),
                    options=_category_options(conn),
                ), 400

            return redirect(url_for('recipe_detail', recipe_id=recipe_id))
        else:
            recipe = conn.execute(text("SELECT * FROM recipe WHERE id=:id"), {'id': recipe_id}).mappings().first()
            ingredients = conn.execute(text('''
                SELECT i.name, ri.amount, ri.unit, ri.note
                FROM recipe_ingredient ri
                JOIN ingredient i ON ri.ingredient_id = i.id
                WHERE ri.recipe_id = :id
            '''), {'id': recipe_id}).mappings().all()
            ingredients_text = "\n".join(
                f"{ing['amount']} {ing['unit']} {ing['name']}".strip()
                for ing in ingredients
            )
            return render_template(
                'edit_recipe.html',
                recipe=recipe,
                ingredients_text=ingredients_text,
                is_new=False,
                options=_category_options(conn),
            )

@app.route('/recipe/new/edit', methods=['GET', 'POST'])
def new_recipe():

    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        ingredients_text = request.form['ingredients']
        instructions = request.form['instructions']
        notes = request.form['notes']
        kitchen = request.form.get('kitchen', '')
        type_ = request.form.get('type', '')
        tags = request.form['tags']

        try:
            with engine.begin() as conn:
                res = conn.execute(text('''
                    INSERT INTO recipe (title, description, instructions, notes, kitchen, type, tags)
                    VALUES (:title, :description, :instructions, :notes, :kitchen, :type, :tags)
                '''), {
                    'title': title, 'description': description, 'instructions': instructions,
                    'notes': notes, 'kitchen': kitchen, 'type': type_, 'tags': tags
                })
                recipe_id = res.lastrowid

            for line in ingredients_text.strip().split('\n'):
                parts = line.strip().split(' ', 2)
                if len(parts) == 3:
                    amount, unit, name = parts
                elif len(parts) == 2:
                    amount, unit = parts
                    name = ''
                elif len(parts) == 1:
                    amount = parts[0]
                    unit = ''
                    name = ''
                else:
                    continue
                ingredient_id = _resolve_ingredient_id(conn, name)
                if ingredient_id is None:
                    raise IngredientNotInCatalog(name, ['grocery_category', 'default_unit'])
                conn.execute(text('''
                    INSERT INTO recipe_ingredient (recipe_id, ingredient_id, amount, unit, note)
                    VALUES (:recipe_id, :ingredient_id, :amount, :unit, :note)
                '''), {
                    'recipe_id': recipe_id, 'ingredient_id': ingredient_id,
                    'amount': amount, 'unit': unit, 'note': ''
                })

            new_ings = conn.execute(text('''
                SELECT i.id AS ingredient_id, i.name, ri.amount, ri.unit, ri.note
                FROM recipe_ingredient ri
                JOIN ingredient i ON ri.ingredient_id = i.id
                WHERE ri.recipe_id = :id
            '''), {'id': recipe_id}).mappings().all()
            conn.execute(text('''
                INSERT INTO recipe_version
                    (recipe_id, version_number, title, description, instructions, notes,
                     tags, type, kitchen, ingredients_json, changed_at, changed_by, change_note)
                VALUES (:recipe_id, 1, :title, :description, :instructions, :notes,
                        :tags, :type, :kitchen, :ings_json, :changed_at, 'web', 'Initial version')
            '''), {
                'recipe_id': recipe_id, 'title': title, 'description': description,
                'instructions': instructions, 'notes': notes,
                'tags': tags, 'type': type_, 'kitchen': kitchen,
                'ings_json': json.dumps([dict(r) for r in new_ings], ensure_ascii=False),
                'changed_at': datetime.now(timezone.utc).isoformat(),
            })
        except IngredientNotInCatalog as e:
            empty_recipe = {
                'id': None, 'title': title, 'description': description,
                'instructions': instructions, 'notes': notes,
                'tags': tags, 'type': type_, 'kitchen': kitchen,
            }
            with engine.connect() as conn:
                opts = _category_options(conn)
            return render_template(
                'edit_recipe.html', recipe=empty_recipe,
                ingredients_text=ingredients_text, is_new=True,
                error=str(e), options=opts,
            ), 400

        return redirect(url_for('recipe_detail', recipe_id=recipe_id))
    else:
        empty_recipe = {
            'id': None, 'title': '', 'description': '', 'instructions': '',
            'notes': '', 'tags': '', 'type': '', 'kitchen': '',
        }
        with engine.connect() as conn:
            opts = _category_options(conn)
        return render_template('edit_recipe.html', recipe=empty_recipe,
                               ingredients_text='', is_new=True,
                               options=opts)

@app.route('/recipe/<int:recipe_id>/delete', methods=['POST'])
def delete_recipe(recipe_id):

    with engine.begin() as conn:
        conn.execute(text('DELETE FROM recipe_ingredient WHERE recipe_id=:id'), {'id': recipe_id})
        conn.execute(text('DELETE FROM recipe WHERE id=:id'), {'id': recipe_id})
    return redirect(url_for('ide_home'))


@app.route('/recipe/<int:recipe_id>/diff')
def recipe_diff(recipe_id):
    # Diff visas numera som flik i IDE:n.
    return redirect(url_for('ide_home') + f'?open={recipe_id}&diff=1')


# ---------------------------------------------------------------------------
# JSON API for the edit-recipe skill (Cowork & Claude Code).
# ---------------------------------------------------------------------------

@app.route('/api/recipe/<int:recipe_id>', methods=['GET'])
def api_recipe_get(recipe_id):
    auth_err = _check_api_token()
    if auth_err is not None:
        return auth_err

    with engine.connect() as conn:
        recipe = conn.execute(
            text("SELECT * FROM recipe WHERE id=:id"), {'id': recipe_id}
        ).mappings().first()
        if not recipe:
            return jsonify({'error': 'Recipe not found'}), 404

        ings = conn.execute(text('''
            SELECT i.id AS ingredient_id, i.name, i.grocery_category,
                   i.default_unit, i.kitchen_staple, i.aliases,
                   ri.amount, ri.unit, ri.note
            FROM recipe_ingredient ri
            JOIN ingredient i ON ri.ingredient_id = i.id
            WHERE ri.recipe_id = :id
            ORDER BY i.name
        '''), {'id': recipe_id}).mappings().all()

        current_version = conn.execute(
            text("SELECT COALESCE(MAX(version_number),0) FROM recipe_version WHERE recipe_id=:id"),
            {'id': recipe_id},
        ).scalar() or 0

    return jsonify({
        'id': recipe['id'],
        'title': recipe['title'],
        'description': recipe['description'],
        'instructions': recipe['instructions'],
        'notes': recipe['notes'],
        'tags': recipe['tags'],
        'type': recipe['type'],
        'kitchen': recipe['kitchen'],
        'current_version_number': current_version,
        'ingredients': [
            {
                'ingredient_id': r['ingredient_id'],
                'name': r['name'],
                'amount': r['amount'],
                'unit': r['unit'],
                'note': r['note'],
                'grocery_category': r['grocery_category'],
                'default_unit': r['default_unit'],
                'kitchen_staple': r['kitchen_staple'],
                'aliases': json.loads(r['aliases'] or '[]'),
            } for r in ings
        ],
    })


@app.route('/api/recipe/search', methods=['GET'])
def api_recipe_search():
    """Lightweight title search so the skill can resolve a name to an id."""
    auth_err = _check_api_token()
    if auth_err is not None:
        return auth_err

    q = (request.args.get('q') or '').strip()
    with engine.connect() as conn:
        if q:
            rows = conn.execute(text(
                "SELECT id, title, type, kitchen FROM recipe "
                "WHERE LOWER(title) LIKE LOWER(:q) ORDER BY title"
            ), {'q': f"%{q}%"}).mappings().all()
        else:
            rows = conn.execute(text(
                "SELECT id, title, type, kitchen FROM recipe ORDER BY title"
            )).mappings().all()
    return jsonify({'results': [dict(r) for r in rows]})


@app.route('/api/recipe/<int:recipe_id>/commit-edit', methods=['POST'])
def api_recipe_commit_edit(recipe_id):
    auth_err = _check_api_token()
    if auth_err is not None:
        return auth_err

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'Body must be a JSON object'}), 400

    change_note = payload.get('change_note')
    if not change_note or not isinstance(change_note, str):
        return jsonify({'error': 'change_note (non-empty string) is required'}), 400

    expected_version = payload.get('expected_version_number')
    if expected_version is not None:
        try:
            expected_version = int(expected_version)
        except (TypeError, ValueError):
            return jsonify({'error': 'expected_version_number must be an integer'}), 400

    allowed = {'title', 'description', 'instructions', 'notes',
               'tags', 'type', 'kitchen', 'ingredients'}
    new_state = {k: v for k, v in payload.items() if k in allowed}

    if 'ingredients' in new_state and new_state['ingredients'] is not None:
        if not isinstance(new_state['ingredients'], list):
            return jsonify({'error': 'ingredients must be a list'}), 400
        for i, ing in enumerate(new_state['ingredients']):
            if not isinstance(ing, dict) or not (ing.get('name') or '').strip():
                return jsonify({'error': f'ingredients[{i}] must have a non-empty name'}), 400

    _backup_before_edit(note=f"api-{recipe_id}")
    try:
        with engine.begin() as conn:
            result = apply_recipe_edit(
                conn, recipe_id, new_state,
                change_note=change_note,
                changed_by=payload.get('changed_by', 'chat'),
                expected_version=expected_version,
            )
    except RecipeNotFound:
        return jsonify({'error': 'Recipe not found'}), 404
    except VersionConflict as e:
        return jsonify({
            'error': 'Version conflict',
            'expected_version_number': e.expected_version,
            'current_version_number': e.current_version,
            'hint': 'Re-fetch the recipe via GET /api/recipe/<id> and rebuild your edit.',
        }), 409
    except IngredientNotInCatalog as e:
        return jsonify({
            'error': 'Ingredient not in catalog',
            'ingredient_name': e.name,
            'missing_fields': e.missing,
            'hint': str(e),
        }), 400
    except SQLAlchemyError as e:
        return jsonify({'error': f'Database error: {e}'}), 500

    return jsonify({
        'ok': True,
        'recipe_id': result['recipe_id'],
        'new_version_number': result['new_version_number'],
        'changed_at': result['changed_at'],
        'change_note': change_note,
    })


@app.route('/api/recipe', methods=['POST'])
def api_recipe_create():
    auth_err = _check_api_token()
    if auth_err is not None:
        return auth_err

    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({'error': 'Body must be a JSON object'}), 400

    title = payload.get('title')
    if not isinstance(title, str) or not title.strip():
        return jsonify({'error': 'title (non-empty string) is required'}), 400

    allowed = {'title', 'description', 'instructions', 'notes',
               'tags', 'type', 'kitchen', 'ingredients'}
    new_state = {k: v for k, v in payload.items() if k in allowed}

    if 'ingredients' in new_state and new_state['ingredients'] is not None:
        if not isinstance(new_state['ingredients'], list):
            return jsonify({'error': 'ingredients must be a list'}), 400
        for i, ing in enumerate(new_state['ingredients']):
            if not isinstance(ing, dict) or not (ing.get('name') or '').strip():
                return jsonify({'error': f'ingredients[{i}] must have a non-empty name'}), 400

    _backup_before_edit(note="api-create")
    try:
        with engine.begin() as conn:
            result = create_recipe(
                conn, new_state,
                changed_by=payload.get('changed_by', 'chat'),
            )
    except IngredientNotInCatalog as e:
        return jsonify({
            'error': 'Ingredient not in catalog',
            'ingredient_name': e.name,
            'missing_fields': e.missing,
            'hint': str(e),
        }), 400
    except SQLAlchemyError as e:
        return jsonify({'error': f'Database error: {e}'}), 500

    return jsonify({
        'ok': True,
        'recipe_id': result['recipe_id'],
        'version_number': result['new_version_number'],
        'changed_at': result['changed_at'],
    }), 201


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=True)
