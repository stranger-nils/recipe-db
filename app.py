from flask import Flask, request, render_template
import sqlite3

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


if __name__ == '__main__':
    app.run(debug=True)
