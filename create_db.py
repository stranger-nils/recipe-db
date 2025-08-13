import sqlite3

conn = sqlite3.connect('recipe.db')
c = conn.cursor()

c.execute('''
CREATE TABLE IF NOT EXISTS recipe (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    ingredients TEXT,
    instructions TEXT
)
''')

conn.commit()
conn.close()