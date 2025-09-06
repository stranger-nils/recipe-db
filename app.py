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
    c = conn.cursor()

    if selected_tags:
        query = "SELECT * FROM recipe WHERE " + " AND ".join(["tags LIKE ?" for _ in selected_tags])
        values = [f"%{tag}%" for tag in selected_tags]
        c.execute(query, values)
    else:
        c.execute("SELECT * FROM recipe")

    recipes = c.fetchall()
    conn.close()
    return render_template('index.html', recipes=recipes, selected_tags=selected_tags)


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
    user_input = request.form['message']

    # Create session history if it doesn't exist yet
    if 'chat_history' not in session:
        session['chat_history'] = [
            {"role": "system", "content": (
                "You are an AI recipe assistant connected to a SQLite database. "
                "You can help users generate, modify, and insert recipes. "
                "When asked to generate SQL, do so based on the current context in the table `recipe` (columns: id, title, description, ingredients, instructions, image_url, tags)."
            )}
        ]

    # Add the user's message to history
    session['chat_history'].append({"role": "user", "content": user_input})

    # Send full history to OpenAI
    response = client.chat.completions.create(
        model="gpt-5",
        messages=session['chat_history']
    )

    reply = response.choices[0].message.content

    # Add assistant's reply to history
    session['chat_history'].append({"role": "assistant", "content": reply})

    # Save session
    session.modified = True

    return reply


@app.route('/recipe/<int:recipe_id>')
def recipe_detail(recipe_id):
    conn = sqlite3.connect('recipe.db')
    c = conn.cursor()
    c.execute("SELECT * FROM recipe WHERE id=?", (recipe_id,))
    recipe = c.fetchone()
    conn.close()
    if recipe:
        return render_template('recipe_detail.html', recipe=recipe)
    else:
        return "Recipe not found", 404

@app.route('/recipe/<int:recipe_id>/edit', methods=['GET', 'POST'])
def edit_recipe(recipe_id):
    conn = sqlite3.connect('recipe.db')
    c = conn.cursor()
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        ingredients = request.form['ingredients']
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
            image_url = current_image_url  # Keep the old image if no new file is uploaded

        c.execute('''
            UPDATE recipe
            SET title=?, description=?, ingredients=?, instructions=?, notes=?, image_url=?, tags=?
            WHERE id=?
        ''', (title, description, ingredients, instructions, notes, image_url, tags, recipe_id))
        conn.commit()
        conn.close()
        return redirect(url_for('recipe_detail', recipe_id=recipe_id))
    else:
        c.execute("SELECT * FROM recipe WHERE id=?", (recipe_id,))
        recipe = c.fetchone()
        conn.close()
        if recipe:
            return render_template('edit_recipe.html', recipe=recipe)
        else:
            return "Recipe not found", 404

@app.route('/recipe/new/edit', methods=['GET', 'POST'])
def new_recipe():
    if request.method == 'POST':
        title = request.form['title']
        description = request.form['description']
        ingredients = request.form['ingredients']
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
        c = conn.cursor()
        c.execute('''
            INSERT INTO recipe (title, description, ingredients, instructions, notes, image_url, tags)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (title, description, ingredients, instructions, notes, image_url, tags))
        recipe_id = c.lastrowid
        conn.commit()
        conn.close()
        return redirect(url_for('recipe_detail', recipe_id=recipe_id))
    else:
        # Empty recipe for the form
        empty_recipe = [None, '', '', '', '', '', '', '']
        return render_template('edit_recipe.html', recipe=empty_recipe, is_new=True)


if __name__ == '__main__':
    app.run(debug=True)
