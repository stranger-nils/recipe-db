from dotenv import load_dotenv
from openai import OpenAI
import os
from flask import Flask, request, render_template, session
from flask_session import Session
import sqlite3

load_dotenv()

client = OpenAI()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY")

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

if __name__ == '__main__':
    app.run(debug=True)
