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


@app.route('/')
def index():
    selected_tags = request.args.getlist('tag')  # Supports multiple tags via ?tag=chicken&tag=swedish
    conn = sqlite3.connect('recipe.db')
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    # Fetch all ingredients for the filter dropdown
    c.execute('SELECT id, name FROM ingredient ORDER BY name')
    all_ingredients = c.fetchall()

    # Get selected ingredient IDs from query params
    selected_ingredients = request.args.getlist('ingredients', type=int)

    # Filter recipes if ingredients are selected
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
    return render_template('index.html', recipes=recipes, all_ingredients=all_ingredients, selected_ingredients=selected_ingredients)


@app.route('/sql', methods=['GET', 'POST'])
def sql_sandbox():
    result = ''
    error = ''
    query = ''
    if request.method == 'POST':
        query = request.form['query']
        try:
            conn = sqlite3.connect('recipe.db')
            c = conn.cursor()
            c.execute(query)

            if query.strip().lower().startswith("select"):
                result = c.fetchall()
            else:
                conn.commit()
                result = "Query executed successfully."

            conn.close()
        except Exception as e:
            error = str(e)

    return render_template('sql.html', result=result, error=error, query=query)


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
            # Insert ingredient if not exists
            c.execute("INSERT OR IGNORE INTO ingredient (name) VALUES (?)", (name,))
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

if __name__ == '__main__':
    app.run(debug=True)
