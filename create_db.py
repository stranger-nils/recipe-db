import sqlite3

conn = sqlite3.connect('recipe.db')
c = conn.cursor()

# c.execute('''
# CREATE TABLE IF NOT EXISTS recipe (
#     id INTEGER PRIMARY KEY AUTOINCREMENT,
#     title TEXT,
#     ingredients TEXT,
#     instructions TEXT
# )
# ''')

c.execute('DROP TABLE IF EXISTS recipe')

c.execute('''
CREATE TABLE recipe (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT,
    description TEXT,
    ingredients TEXT,
    instructions TEXT,
    image_url TEXT,
    tags TEXT
)
''')

# Lägg till ett exempelrecept
c.execute('''
INSERT INTO recipe (title, description, ingredients, instructions, image_url, tags)
VALUES (?, ?, ?, ?, ?, ?)
''', (
    'Köttbullar med potatismos',
    'Klassisk svensk husmanskost med gräddsås och lingon.',
    'köttfärs, potatis, mjölk, smör, grädde, lök, ägg, ströbröd, salt, peppar',
    '1. Blanda köttfärs med ägg, lök, ströbröd, kryddor. Forma till bollar och stek.\n2. Skala och koka potatis. Mosa med mjölk och smör.\n3. Servera med gräddsås och lingonsylt.',
    'https://example.com/kottbullar.jpg',  # Ändra till riktig bildlänk om du vill
    'husmanskost,kött,potatis'
))


conn.commit()
conn.close()