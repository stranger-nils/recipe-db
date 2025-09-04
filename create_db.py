# import sqlite3

# conn = sqlite3.connect('recipe.db')
# c = conn.cursor()

# c.execute('DROP TABLE IF EXISTS recipe')

# c.execute('''
# CREATE TABLE recipe (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     title TEXT,
#     description TEXT,
#     ingredients TEXT,
#     instructions TEXT,
#     image_url TEXT,
#     tags TEXT
# )
# ''')

# conn.commit()
# conn.close()