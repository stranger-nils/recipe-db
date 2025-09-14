from dotenv import load_dotenv
from openai import OpenAI
import os
from flask import Flask, request, render_template, session, redirect, url_for
from flask_session import Session
import sqlite3
from werkzeug.utils import secure_filename

load_dotenv()

client = OpenAI()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

UPLOAD_FOLDER = 'static/uploads'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Use server-side session storage
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

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
    conn = sqlite3.connect('recipe.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    # Fetch all ingredients for the filter dropdown
    c.execute('SELECT id, name FROM ingredient ORDER BY name')
    all_ingredients = c.fetchall()

    selected_ingredients = request.args.getlist('ingredients', type=int)
    advanced_sql = None
    recipes = []
    error = None

    if request.method == 'POST' and 'sql_query' in request.form:
        advanced_sql = request.form['sql_query']
        try:
            c.execute(advanced_sql)
            recipes = c.fetchall()
        except Exception as e:
            error = str(e)
            recipes = []
    else:
        if selected_ingredients:
            placeholders = ','.join('?' for _ in selected_ingredients)
            query = f'''
                SELECT DISTINCT r.*
                FROM recipe r
                JOIN recipe_ingredient ri ON r.id = ri.recipe_id
                WHERE ri.ingredient_id IN ({placeholders})
            '''
            c.execute(query, selected_ingredients)
            recipes = c.fetchall()
        else:
            c.execute('SELECT * FROM recipe')
            recipes = c.fetchall()

    conn.close()
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
            conn = sqlite3.connect('recipe.db')
            conn.row_factory = sqlite3.Row
            c = conn.cursor()

            c.execute(query)
            if query.strip().lower().startswith("select"):
                rows = c.fetchall()
                result = [dict(row) for row in rows]
                columns = rows[0].keys() if rows else []
            else:
                conn.commit()
                result = [{"Message": "Query executed successfully."}]
                columns = ["Message"]

            conn.close()
        except Exception as e:
            error = str(e)
            result = []
            columns = []

    return render_template('sql.html', result=result, error=error, query=query, columns=columns)

@app.route('/chat', methods=['POST'])
def chat():
    user_input = request.form['message'].strip()

    # System prompt with persona + strict recipe format contract
    SYSTEM_PROMPT = (
        "You are René, an AI sous chef. "
        "Your role is to support the user (the head chef) with professional, accurate, and encouraging culinary help. "
        "Be concise by default; expand with steps or deeper detail when asked. "
        "Offer small, thoughtful improvements (seasoning, technique, presentation) without being bossy. "
        "Use a warm, confident tone; light culinary metaphors are okay. End with a supportive note when it fits.\n\n"
        "RECIPE OUTPUT CONTRACT (IMPORTANT):\n"
        "- If the user asks for a recipe, a variation of a recipe, or a full method for a dish, "
        "you MUST output exactly two sections with these exact headings:\n"
        "Ingredients:\n"
        "Instructions:\n"
        "- Under 'Ingredients:', list one ingredient per line in the form: "
        "\"<amount> <unit> <ingredient>\" (no bullets). Examples: \"200 g spaghetti\", \"1 tbsp olive oil\". "
        "If unit is not applicable, omit it: \"1 lemon\".\n"
        "- Under 'Instructions:', provide a numbered method using Arabic numerals, like:\n"
        "1. Step one\n"
        "2. Step two\n"
        "3. ...\n"
        "- Do not include any other sections (no 'Notes', no 'Servings') unless the user explicitly asks.\n"
        "- If the user asks only for ideas/tips (not a full recipe), answer normally without the two sections.\n"
        "- If the user asks for partial info (e.g., only ingredients), supply only what was asked — still honoring the format where relevant.\n"
    )

    # Create session history if it doesn't exist yet
    if 'chat_history' not in session:
        session['chat_history'] = [
            {"role": "system", "content": SYSTEM_PROMPT}
        ]

    # Append user message
    session['chat_history'].append({"role": "user", "content": user_input})

    # Call OpenAI
    response = client.chat.completions.create(
            model="gpt-5",
            messages=session['chat_history']
        )
    reply = response.choices[0].message.content

    # Append assistant reply and persist session
    session['chat_history'].append({"role": "assistant", "content": reply})
    
    # Save session
    session.modified = True

    return reply



@app.route('/recipe/<int:recipe_id>')
def recipe_detail(recipe_id):
    conn = sqlite3.connect('recipe.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # Fetch the recipe
    c.execute('SELECT * FROM recipe WHERE id=?', (recipe_id,))
    recipe = c.fetchone()
    # Fetch the ingredients for this recipe
    c.execute('''
        SELECT i.name, ri.amount, ri.unit, ri.note
        FROM recipe_ingredient ri
        JOIN ingredient i ON ri.ingredient_id = i.id
        WHERE ri.recipe_id = ?
    ''', (recipe_id,))
    ingredients = c.fetchall()
    conn.close()
    return render_template('recipe_detail.html', recipe=recipe, ingredients=ingredients)

@app.route('/recipe/<int:recipe_id>/edit', methods=['GET', 'POST'])
def edit_recipe(recipe_id):
    conn = sqlite3.connect('recipe.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        ingredients_text = request.form['ingredients']
        instructions = request.form['instructions']
        notes = request.form['notes']
        tags = request.form['tags']

        # Get the current image_url from the database
        c.execute("SELECT image_url FROM recipe WHERE id=?", (recipe_id,))
        current_image_url = c.fetchone()[0]

        # Handle file upload
        file = request.files.get('image_file')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            image_url = '/' + filepath.replace('\\', '/')
        else:
            image_url = current_image_url

        c.execute('''
            UPDATE recipe
            SET title=?, description=?, instructions=?, notes=?, image_url=?, tags=?
            WHERE id=?
        ''', (title, description, instructions, notes, image_url, tags, recipe_id))

        # Remove old ingredients for this recipe
        c.execute("DELETE FROM recipe_ingredient WHERE recipe_id=?", (recipe_id,))

        # Parse and insert new ingredients
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
            c.execute("INSERT OR IGNORE INTO ingredient (name) VALUES (?)", (name,))
            c.execute("SELECT id FROM ingredient WHERE name=?", (name,))
            ingredient_id = c.fetchone()[0]
            c.execute('''
                INSERT INTO recipe_ingredient (recipe_id, ingredient_id, amount, unit, note)
                VALUES (?, ?, ?, ?, ?)
            ''', (recipe_id, ingredient_id, amount, unit, ''))

        conn.commit()
        conn.close()
        return redirect(url_for('recipe_detail', recipe_id=recipe_id))
    else:
        c.execute("SELECT * FROM recipe WHERE id=?", (recipe_id,))
        recipe = c.fetchone()

        # Fetch ingredients for this recipe
        c.execute('''
            SELECT i.name, ri.amount, ri.unit, ri.note
            FROM recipe_ingredient ri
            JOIN ingredient i ON ri.ingredient_id = i.id
            WHERE ri.recipe_id = ?
        ''', (recipe_id,))
        ingredients = c.fetchall()

        # Prepare a string for the textarea (e.g., "2 tbsp olive oil\n1 onion")
        ingredients_text = "\n".join(
            f"{ing['amount']} {ing['unit']} {ing['name']}".strip()
            for ing in ingredients
        )

        # Pass ingredients_text to the template
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
        tags = request.form['tags']

        image_url = ''
        file = request.files.get('image_file')
        if file and allowed_file(file.filename):
            filename = secure_filename(file.filename)
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            image_url = '/' + filepath.replace('\\', '/')

        conn = sqlite3.connect('recipe.db')
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        # Insert recipe
        c.execute('''
            INSERT INTO recipe (title, description, instructions, notes, image_url, tags)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (title, description, instructions, notes, image_url, tags))
        recipe_id = c.lastrowid

        # Parse and insert ingredients
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
            # Insert ingredient if not exists, always set grocery_category and notes to empty string if new
            c.execute(
                "INSERT OR IGNORE INTO ingredient (name, grocery_category, notes) VALUES (?, ?, ?)",
                (name, '', '')
            )
            c.execute("SELECT id FROM ingredient WHERE name=?", (name,))
            ingredient_id = c.fetchone()[0]
            # Insert into recipe_ingredient
            c.execute('''
                INSERT INTO recipe_ingredient (recipe_id, ingredient_id, amount, unit, note)
                VALUES (?, ?, ?, ?, ?)
            ''', (recipe_id, ingredient_id, amount, unit, ''))

        conn.commit()
        conn.close()
        return redirect(url_for('recipe_detail', recipe_id=recipe_id))
    else:
        empty_recipe = [None, '', '', '', '', '', '', '']
        return render_template('edit_recipe.html', recipe=empty_recipe, is_new=True)

@app.route('/recipe/<int:recipe_id>/delete', methods=['POST'])
def delete_recipe(recipe_id):
    conn = sqlite3.connect('recipe.db')
    c = conn.cursor()
    # Delete from recipe_ingredient first (to avoid foreign key constraint issues)
    c.execute('DELETE FROM recipe_ingredient WHERE recipe_id=?', (recipe_id,))
    # Delete the recipe itself
    c.execute('DELETE FROM recipe WHERE id=?', (recipe_id,))
    conn.commit()
    conn.close()
    return redirect(url_for('index'))

@app.route('/add_to_shopping_list/<int:recipe_id>', methods=['POST'])
def add_to_shopping_list(recipe_id):
    shopping_list = session.get('shopping_list', {})
    shopping_list[str(recipe_id)] = shopping_list.get(str(recipe_id), 0) + 1
    session['shopping_list'] = shopping_list
    return redirect(url_for('shopping_list'))

@app.route('/shopping_list', methods=['GET', 'POST'])
def shopping_list():
    conn = sqlite3.connect('recipe.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    shopping_list = session.get('shopping_list', {})
    recipes = []
    ingredients_map = {}

    for recipe_id, qty in shopping_list.items():
        c.execute('SELECT * FROM recipe WHERE id=?', (recipe_id,))
        recipe = c.fetchone()
        if recipe:
            recipes.append({'recipe': recipe, 'qty': qty})

            # Fetch ingredients for this recipe, including grocery_category and kitchen_staple
            c.execute('''
                SELECT i.name, ri.amount, ri.unit, i.grocery_category, i.kitchen_staple
                FROM recipe_ingredient ri
                JOIN ingredient i ON ri.ingredient_id = i.id
                WHERE ri.recipe_id = ?
            ''', (recipe_id,))
            for ing in c.fetchall():
                key = (ing['name'], ing['unit'], ing['grocery_category'], ing['kitchen_staple'])
                try:
                    amt = float(ing['amount']) * qty
                except:
                    amt = f"{ing['amount']} x {qty}"
                if key in ingredients_map:
                    try:
                        ingredients_map[key] += amt
                    except:
                        ingredients_map[key] = f"{ingredients_map[key]}, {amt}"
                else:
                    ingredients_map[key] = amt

    # Convert ingredients_map to a list of tuples for sorting
    sorted_items = sorted(
        ingredients_map.items(),
        key=lambda item: (
            not item[0][3],                # kitchen_staple: True first
            item[0][2] or '',              # grocery_category (was group)
            item[0][0]                     # name
        )
    )

    conn.close()
    return render_template('shopping_list.html', recipes=recipes, sorted_items=sorted_items)

@app.route('/update_shopping_list/<int:recipe_id>/<action>', methods=['POST'])
def update_shopping_list(recipe_id, action):
    shopping_list = session.get('shopping_list', {})
    rid = str(recipe_id)
    if rid in shopping_list:
        if action == 'increase':
            shopping_list[rid] += 1
        elif action == 'decrease':
            shopping_list[rid] = max(1, shopping_list[rid] - 1)
    session['shopping_list'] = shopping_list
    return redirect(url_for('shopping_list'))

@app.route('/remove_from_shopping_list/<int:recipe_id>', methods=['POST'])
def remove_from_shopping_list(recipe_id):
    shopping_list = session.get('shopping_list', {})
    rid = str(recipe_id)
    if rid in shopping_list:
        del shopping_list[rid]
    session['shopping_list'] = shopping_list
    return redirect(url_for('shopping_list'))

@app.route('/ingredient_library', methods=['GET', 'POST'])
def ingredient_library():
    conn = sqlite3.connect('recipe.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    if request.method == 'POST':
        # Fetch all ingredient IDs in the table
        c.execute('''
            SELECT DISTINCT i.id
            FROM ingredient i
            JOIN recipe_ingredient ri ON i.id = ri.ingredient_id
        ''')
        ingredient_ids = [row['id'] for row in c.fetchall()]

        for ing_id in ingredient_ids:
            grocery_category = request.form.get(f'grocery_category_{ing_id}', '')
            notes = request.form.get(f'notes_{ing_id}', '')
            kitchen_staple = 1 if request.form.get(f'kitchen_staple_{ing_id}') == 'on' else 0
            c.execute(
                'UPDATE ingredient SET grocery_category=?, notes=?, kitchen_staple=? WHERE id=?',
                (grocery_category, notes, kitchen_staple, ing_id)
            )
        conn.commit()

    # Fetch all ingredients used in any recipe
    c.execute('''
        SELECT DISTINCT i.*
        FROM ingredient i
        JOIN recipe_ingredient ri ON i.id = ri.ingredient_id
        ORDER BY i.name
    ''')
    ingredients = c.fetchall()

    # For each ingredient, fetch the recipe IDs where it's used
    ingredient_recipes = {}
    for ing in ingredients:
        c.execute('SELECT recipe_id FROM recipe_ingredient WHERE ingredient_id=?', (ing['id'],))
        recipe_ids = [str(row['recipe_id']) for row in c.fetchall()]
        ingredient_recipes[ing['id']] = ', '.join(recipe_ids)

    conn.close()
    return render_template('ingredient_library.html', ingredients=ingredients, ingredient_recipes=ingredient_recipes)

if __name__ == '__main__':
    app.run(debug=True)
