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


@app.route('/', methods=['GET', 'POST'])
def index():

    with engine.connect() as conn:
        all_ingredients = conn.execute(text('SELECT id, name FROM ingredient ORDER BY name')).mappings().all()

        selected_ingredients = request.args.getlist('ingredients', type=int)
        group_by = request.args.get('group_by', 'none')
        if group_by not in GROUP_BY_OPTIONS:
            group_by = 'none'

        advanced_sql = None
        recipes = []
        error = None

        if request.method == 'POST' and 'sql_query' in request.form:
            advanced_sql = request.form['sql_query']
            try:
                result = conn.execute(text(advanced_sql))
                recipes = result.mappings().all()
            except SQLAlchemyError as e:
                error = str(e)
                recipes = []
        else:
            if selected_ingredients:
                placeholders = ','.join(f':id{i}' for i in range(len(selected_ingredients)))
                query = f'''
                    SELECT DISTINCT r.*
                    FROM recipe r
                    JOIN recipe_ingredient ri ON r.id = ri.recipe_id
                    WHERE ri.ingredient_id IN ({placeholders})
                    ORDER BY r.title
                '''
                params = {f'id{i}': v for i, v in enumerate(selected_ingredients)}
                recipes = conn.execute(text(query), params).mappings().all()
            else:
                recipes = conn.execute(text('SELECT * FROM recipe ORDER BY title')).mappings().all()

    # Group if requested.
    grouped = None
    if group_by in ('kitchen', 'type'):
        buckets = {}
        for r in recipes:
            key = (r[group_by] or '').strip() or '(Ej angiven)'
            buckets.setdefault(key, []).append(r)
        grouped = sorted(buckets.items(), key=lambda kv: kv[0].lower())

    return render_template(
        'index.html',
        recipes=recipes,
        grouped=grouped,
        group_by=group_by,
        all_ingredients=all_ingredients,
        selected_ingredients=selected_ingredients,
        advanced_sql=advanced_sql,
        error=error,
        default_sql_query=default_sql_query
    )

@app.route('/sql', methods=['GET', 'POST'])
def sql_sandbox():
    result = []
    error = ''
    query = ''
    columns = []

    if request.method == 'POST':
        query = request.form['query']
        try:
            with engine.begin() as conn:
                res = conn.execute(text(query))
                if query.strip().lower().startswith("select"):
                    rows = res.mappings().all()
                    result = [dict(row) for row in rows]
                    columns = rows[0].keys() if rows else []
                else:
                    result = [{"Message": "Query executed successfully."}]
                    columns = ["Message"]
        except SQLAlchemyError as e:
            error = str(e)
            result = []
            columns = []

    return render_template('sql.html', result=result, error=error, query=query, columns=columns)

@app.route('/recipe/<int:recipe_id>')
def recipe_detail(recipe_id):

    with engine.connect() as conn:
        recipe = conn.execute(text('SELECT * FROM recipe WHERE id=:id'), {'id': recipe_id}).mappings().first()
        ingredients = conn.execute(text('''
            SELECT i.name, ri.amount, ri.unit, ri.note
            FROM recipe_ingredient ri
            JOIN ingredient i ON ri.ingredient_id = i.id
            WHERE ri.recipe_id = :id
        '''), {'id': recipe_id}).mappings().all()
    return render_template('recipe_detail.html', recipe=recipe, ingredients=ingredients)

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
    return redirect(url_for('index'))

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
                    continue  # CHECK constraint skulle ändå reject:a
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

        ingredients = conn.execute(text(
            'SELECT * FROM ingredient ORDER BY name COLLATE NOCASE'
        )).mappings().all()

        ingredient_recipes = {}
        ingredient_aliases = {}
        for ing in ingredients:
            recipe_ids = [
                str(row['recipe_id']) for row in conn.execute(
                    text('SELECT recipe_id FROM recipe_ingredient WHERE ingredient_id=:id'), {'id': ing['id']}
                ).mappings().all()
            ]
            ingredient_recipes[ing['id']] = ', '.join(recipe_ids)
            try:
                aliases = json.loads(ing['aliases'] or '[]')
            except (TypeError, ValueError):
                aliases = []
            ingredient_aliases[ing['id']] = ', '.join(aliases)

    return render_template(
        'ingredient_library.html',
        ingredients=ingredients,
        ingredient_recipes=ingredient_recipes,
        ingredient_aliases=ingredient_aliases,
        allowed_categories=sorted(ALLOWED_GROCERY_CATEGORIES),
    )

@app.route('/recipe/<int:recipe_id>/history')
def recipe_history(recipe_id):
    with engine.connect() as conn:
        recipe = conn.execute(
            text("SELECT id, title FROM recipe WHERE id=:id"), {'id': recipe_id}
        ).mappings().first()
        if not recipe:
            return "Recipe not found", 404
        versions = conn.execute(text('''
            SELECT id, version_number, changed_at, changed_by, change_note, title
            FROM recipe_version WHERE recipe_id=:id ORDER BY version_number DESC
        '''), {'id': recipe_id}).mappings().all()
    return render_template('recipe_history.html', recipe=recipe, versions=versions)


@app.route('/recipe/<int:recipe_id>/diff')
def recipe_diff(recipe_id):
    v_from = request.args.get('from', type=int)
    v_to = request.args.get('to', type=int)
    with engine.connect() as conn:
        recipe = conn.execute(
            text("SELECT id, title FROM recipe WHERE id=:id"), {'id': recipe_id}
        ).mappings().first()
        if not recipe:
            return "Recipe not found", 404

        if v_from is None or v_to is None:
            versions = conn.execute(text('''
                SELECT version_number FROM recipe_version WHERE recipe_id=:id ORDER BY version_number
            '''), {'id': recipe_id}).mappings().all()
            nums = [v['version_number'] for v in versions]
            if len(nums) < 2:
                return render_template('recipe_diff.html', recipe=recipe,
                                       error="Behöver minst 2 versioner för att visa diff.", diff=None)
            v_from, v_to = nums[-2], nums[-1]

        ver_a = conn.execute(text(
            "SELECT * FROM recipe_version WHERE recipe_id=:rid AND version_number=:v"
        ), {'rid': recipe_id, 'v': v_from}).mappings().first()
        ver_b = conn.execute(text(
            "SELECT * FROM recipe_version WHERE recipe_id=:rid AND version_number=:v"
        ), {'rid': recipe_id, 'v': v_to}).mappings().first()

        if not ver_a or not ver_b:
            return "Version not found", 404

    text_fields = ['title', 'description', 'instructions', 'notes', 'tags', 'type', 'kitchen']
    field_diffs = {}
    for f in text_fields:
        a_val = ver_a[f] or ''
        b_val = ver_b[f] or ''
        if a_val != b_val:
            a_lines = a_val.splitlines(keepends=True)
            b_lines = b_val.splitlines(keepends=True)
            diff_lines = list(difflib.ndiff(a_lines, b_lines))
            field_diffs[f] = diff_lines

    ings_a = {i['name']: i for i in json.loads(ver_a['ingredients_json'] or '[]')}
    ings_b = {i['name']: i for i in json.loads(ver_b['ingredients_json'] or '[]')}
    all_names = sorted(set(ings_a) | set(ings_b))
    ing_diff = []
    for name in all_names:
        if name in ings_a and name in ings_b:
            a, b = ings_a[name], ings_b[name]
            if a.get('amount') != b.get('amount') or a.get('unit') != b.get('unit') or a.get('note') != b.get('note'):
                ing_diff.append(('changed', name, ings_a[name], ings_b[name]))
            else:
                ing_diff.append(('same', name, ings_a[name], ings_b[name]))
        elif name in ings_a:
            ing_diff.append(('removed', name, ings_a[name], None))
        else:
            ing_diff.append(('added', name, None, ings_b[name]))

    return render_template('recipe_diff.html', recipe=recipe,
                           ver_a=ver_a, ver_b=ver_b,
                           field_diffs=field_diffs, ing_diff=ing_diff,
                           v_from=v_from, v_to=v_to)


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


@app.route('/shopping-list', methods=['GET', 'POST'])
def shopping_list():
    with engine.connect() as conn:
        recipes = conn.execute(text(
            "SELECT id, title FROM recipe ORDER BY title"
        )).mappings().all()

    if request.method == 'GET':
        return render_template('shopping_list.html', recipes=recipes,
                               result=None, selected_ids=[])

    selected_ids = [int(x) for x in request.form.getlist('recipe_ids') if x.isdigit()]
    hide_staples = request.form.get('hide_staples') == '1'

    if not selected_ids:
        return render_template('shopping_list.html', recipes=recipes,
                               result=None, selected_ids=[], hide_staples=hide_staples,
                               error="Välj minst ett recept.")

    with engine.connect() as conn:
        placeholders = ','.join([':id' + str(i) for i in range(len(selected_ids))])
        params = {f'id{i}': v for i, v in enumerate(selected_ids)}
        rows = conn.execute(text(f'''
            SELECT i.name, i.grocery_category, i.kitchen_staple,
                   ri.amount, ri.unit
            FROM recipe_ingredient ri
            JOIN ingredient i ON ri.ingredient_id = i.id
            WHERE ri.recipe_id IN ({placeholders})
        '''), params).mappings().all()

        selected_recipes = conn.execute(text(f'''
            SELECT id, title FROM recipe WHERE id IN ({placeholders})
        '''), params).mappings().all()

    from collections import defaultdict
    agg = defaultdict(lambda: {'amounts': [], 'grocery_category': '', 'kitchen_staple': 0})
    for row in rows:
        key = (row['name'].strip().lower(), (row['unit'] or '').strip().lower())
        entry = agg[key]
        entry['display_name'] = row['name']
        entry['grocery_category'] = row['grocery_category'] or 'Övrigt'
        entry['kitchen_staple'] = row['kitchen_staple'] or 0
        entry['unit'] = row['unit'] or ''
        try:
            entry['amounts'].append(float(row['amount'] or 0))
        except (ValueError, TypeError):
            entry['amounts'].append(row['amount'] or '')

    items = []
    for (name_norm, unit_norm), entry in agg.items():
        amounts = entry['amounts']
        if all(isinstance(a, float) for a in amounts):
            total = sum(amounts)
            amount_str = str(int(total)) if total == int(total) else str(total)
        else:
            amount_str = ' + '.join(str(a) for a in amounts if a)

        items.append({
            'name': entry['display_name'],
            'amount': amount_str,
            'unit': entry['unit'],
            'grocery_category': entry['grocery_category'],
            'kitchen_staple': entry['kitchen_staple'],
        })

    items.sort(key=lambda x: (x['grocery_category'], x['name']))

    from itertools import groupby
    grouped = []
    for cat, group in groupby(items, key=lambda x: x['grocery_category']):
        grouped.append((cat, list(group)))

    return render_template('shopping_list.html', recipes=recipes,
                           result=grouped, selected_ids=selected_ids,
                           selected_recipes=selected_recipes,
                           hide_staples=hide_staples)


if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=True)
