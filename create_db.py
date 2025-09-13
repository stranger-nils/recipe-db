import sqlite3

conn = sqlite3.connect('recipe.db')
c = conn.cursor()

# c.execute('DROP TABLE IF EXISTS recipe_ingredient')
c.execute('DROP TABLE IF EXISTS ingredient')
# c.execute('DROP TABLE IF EXISTS recipe')

# c.execute('''
# CREATE TABLE recipe (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     title TEXT,
#     description TEXT,
#     instructions TEXT,
#     notes TEXT,
#     image_url TEXT,
#     tags TEXT
# )
# ''')

c.execute('''
CREATE TABLE ingredient (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT UNIQUE
)
''')

# c.execute('''
# CREATE TABLE recipe_ingredient (
#     recipe_id INTEGER,
#     ingredient_id INTEGER,
#     amount TEXT,
#     unit TEXT,
#     note TEXT,
#     FOREIGN KEY(recipe_id) REFERENCES recipe(id),
#     FOREIGN KEY(ingredient_id) REFERENCES ingredient(id)
# )
# ''')

conn.commit()
conn.close()