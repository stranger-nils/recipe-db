from dotenv import load_dotenv
import os
from flask import Flask, request, render_template, redirect, url_for
from werkzeug.utils import secure_filename
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Result
from sqlalchemy.exc import SQLAlchemyError
from supabase import create_client, Client

load_dotenv()

app = Flask(__name__)

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL")

# If DATABASE_URL is set to SQLite, use it for local dev
if DATABASE_URL and DATABASE_URL.startswith("sqlite"):
    engine = create_engine(DATABASE_URL, future=True, pool_pre_ping=True)
else:
    TURSO_DB_URL = os.getenv("TURSO_DB_URL")
    TURSO_DB_AUTH_TOKEN = os.getenv("TURSO_DB_AUTH_TOKEN")
    engine = create_engine(
        f"sqlite+{TURSO_DB_URL}?secure=true",
        connect_args={"auth_token": TURSO_DB_AUTH_TOKEN},
        pool_pre_ping=True,
        future=True,
    )

USE_SUPABASE = not (DATABASE_URL and DATABASE_URL.startswith("sqlite"))
if USE_SUPABASE:
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_API_KEY = os.getenv("SUPABASE_API_KEY")
    from supabase import create_client, Client
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_API_KEY)
    SUPABASE_BUCKET = "recipe-images"


default_sql_query = (
    "SELECT DISTINCT\n"
    "    recipe_id,\n"
    "    title,\n"
    "    description,\n"
    "    instructions,\n"
    "    notes,\n"
    "    image_url,\n"
    "    tags\n"
    "FROM recipe_with_ingredients\n"
    "WHERE 1=1\n"
    "    -- AND ingredient_name = ...\n"
)

@app.route('/', methods=['GET', 'POST'])
def index():
    
    with engine.connect() as conn:
        # Fetch all ingredients for the filter dropdown
        all_ingredients = conn.execute(text('SELECT id, name FROM ingredient ORDER BY name')).mappings().all()

        selected_ingredients = request.args.getlist('ingredients', type=int)
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
                '''
                params = {f'id{i}': v for i, v in enumerate(selected_ingredients)}
                recipes = conn.execute(text(query), params).mappings().all()
            else:
                recipes = conn.execute(text('SELECT * FROM recipe')).mappings().all()

    return render_template(
        'index.html',
        recipes=recipes,
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

@app.route('/recipe/<int:recipe_id>/edit', methods=['GET', 'POST'])
def edit_recipe(recipe_id):
    
    with engine.begin() as conn:
        if request.method == 'POST':
            title = request.form['title']
            description = request.form['description']
            ingredients_text = request.form['ingredients']
            instructions = request.form['instructions']
            notes = request.form['notes']
            menu = request.form['menu']
            section = request.form['section']
            tags = request.form['tags']

            current_image_url = conn.execute(
                text("SELECT image_url FROM recipe WHERE id=:id"), {'id': recipe_id}
            ).scalar()

            file = request.files.get('image_file')
            if file and allowed_file(file.filename):
                filename = secure_filename(file.filename)
                if USE_SUPABASE:
                    file_bytes = file.read()
                    supabase.storage.from_(SUPABASE_BUCKET).upload(filename, file_bytes)
                    image_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(filename)
                else:
                    local_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                    file.save(local_path)
                    image_url = f"/static/uploads/{filename}"
            else:
                image_url = current_image_url if 'current_image_url' in locals() else ''

            conn.execute(text('''
                UPDATE recipe
                SET title=:title, description=:description, instructions=:instructions, notes=:notes, image_url=:image_url, menu=:menu, section=:section, tags=:tags
                WHERE id=:id
            '''), {
                'title': title, 'description': description, 'instructions': instructions,
                'notes': notes, 'image_url': image_url, 'menu': menu, 'section': section, 'tags': tags, 'id': recipe_id
            })

            conn.execute(text("DELETE FROM recipe_ingredient WHERE recipe_id=:id"), {'id': recipe_id})

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
                conn.execute(text("INSERT OR IGNORE INTO ingredient (name) VALUES (:name)"), {'name': name})
                ingredient_id = conn.execute(text("SELECT id FROM ingredient WHERE name=:name"), {'name': name}).scalar()
                conn.execute(text('''
                    INSERT INTO recipe_ingredient (recipe_id, ingredient_id, amount, unit, note)
                    VALUES (:recipe_id, :ingredient_id, :amount, :unit, :note)
                '''), {
                    'recipe_id': recipe_id, 'ingredient_id': ingredient_id,
                    'amount': amount, 'unit': unit, 'note': ''
                })

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
                is_new=False
            )

@app.route('/recipe/new/edit', methods=['GET', 'POST'])
def new_recipe():
    
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        ingredients_text = request.form['ingredients']
        instructions = request.form['instructions']
        notes = request.form['notes']
        menu = request.form['menu']
        section = request.form['section']
        tags = request.form['tags']

        # Handle image upload
        image_url = ''
        file = request.files.get('image_file')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            if USE_SUPABASE:
                file_bytes = file.read()
                supabase.storage.from_(SUPABASE_BUCKET).upload(filename, file_bytes)
                image_url = supabase.storage.from_(SUPABASE_BUCKET).get_public_url(filename)
            else:
                local_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(local_path)
                image_url = f"/static/uploads/{filename}"


        # Insert new recipe
        with engine.begin() as conn:
            res = conn.execute(text('''
                INSERT INTO recipe (title, description, instructions, notes, menu, section, image_url, tags)
                VALUES (:title, :description, :instructions, :notes, :menu, :section, :image_url, :tags)
            '''), {
                'title': title, 'description': description, 'instructions': instructions,
                'notes': notes, 'menu': menu, 'section': section, 'image_url': image_url, 'tags': tags
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
                conn.execute(
                    text("INSERT OR IGNORE INTO ingredient (name, grocery_category, notes) VALUES (:name, '', '')"),
                    {'name': name}
                )
                ingredient_id = conn.execute(text("SELECT id FROM ingredient WHERE name=:name"), {'name': name}).scalar()
                conn.execute(text('''
                    INSERT INTO recipe_ingredient (recipe_id, ingredient_id, amount, unit, note)
                    VALUES (:recipe_id, :ingredient_id, :amount, :unit, :note)
                '''), {
                    'recipe_id': recipe_id, 'ingredient_id': ingredient_id,
                    'amount': amount, 'unit': unit, 'note': ''
                })

        return redirect(url_for('recipe_detail', recipe_id=recipe_id))
    else:
        empty_recipe = [None, '', '', '', '', '', '', '']
        return render_template('edit_recipe.html', recipe=empty_recipe, is_new=True)

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
                row['id'] for row in conn.execute(text('''
                    SELECT DISTINCT i.id
                    FROM ingredient i
                    JOIN recipe_ingredient ri ON i.id = ri.ingredient_id
                ''')).mappings().all()
            ]
            for ing_id in ingredient_ids:
                grocery_category = request.form.get(f'grocery_category_{ing_id}', '')
                notes = request.form.get(f'notes_{ing_id}', '')
                kitchen_staple = 1 if request.form.get(f'kitchen_staple_{ing_id}') == 'on' else 0
                conn.execute(
                    text('UPDATE ingredient SET grocery_category=:gc, notes=:notes, kitchen_staple=:ks WHERE id=:id'),
                    {'gc': grocery_category, 'notes': notes, 'ks': kitchen_staple, 'id': ing_id}
                )

        ingredients = conn.execute(text('''
            SELECT DISTINCT i.*
            FROM ingredient i
            JOIN recipe_ingredient ri ON i.id = ri.ingredient_id
            ORDER BY i.name
        ''')).mappings().all()

        ingredient_recipes = {}
        for ing in ingredients:
            recipe_ids = [
                str(row['recipe_id']) for row in conn.execute(
                    text('SELECT recipe_id FROM recipe_ingredient WHERE ingredient_id=:id'), {'id': ing['id']}
                ).mappings().all()
            ]
            ingredient_recipes[ing['id']] = ', '.join(recipe_ids)

    return render_template('ingredient_library.html', ingredients=ingredients, ingredient_recipes=ingredient_recipes)

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5001)), debug=True)