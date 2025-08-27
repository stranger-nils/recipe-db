from dotenv import load_dotenv
from openai import OpenAI
import os
from flask import Flask, request, render_template
import sqlite3

load_dotenv()

client = OpenAI()

app = Flask(__name__)

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

    system_prompt = """
You are an AI recipe assistant connected to a SQLite database with the table `recept` (columns: id, title, description, ingredients, instructions, image_url, tags).
You can help generate new recipes, modify existing ones, or answer questions about what's in the database.

Respond with clear, useful suggestions and SQL queries if asked.
If a user wants to insert a recipe, return the recipe as a Python dictionary ready for insertion.
"""

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input}
    ]

    response = client.chat.completions.create(
        model="gpt-5",
        messages=messages
    )

    reply = response.choices[0].message.content

    return reply

if __name__ == '__main__':
    app.run(debug=True)
