"""
Bootstrap script: create a local SQLite database from CSV files in scripts/.

Usage:
1. Place your CSV files (recipe.csv, ingredient.csv, recipe_ingredient.csv) in the scripts/ folder.
2. Run: python scripts/csv_to_sqlite.py
"""
import os
import sqlite3
import pandas as pd

SQLITE_DB_PATH = os.getenv("SQLITE_DB_PATH", "recipe.db")
CSV_FOLDER = os.path.join(os.path.dirname(__file__))

TABLES = [
    ("recipe", "recipe.csv"),
    ("ingredient", "ingredient.csv"),
    ("recipe_ingredient", "recipe_ingredient.csv")
]

def import_csv_to_sqlite(table_name, csv_file, conn):
    csv_path = os.path.join(CSV_FOLDER, csv_file)
    print(f"Importing {csv_path} into table '{table_name}'...")
    df = pd.read_csv(csv_path)
    df.to_sql(table_name, conn, if_exists='replace', index=False)
    print(f"{table_name}: {len(df)} rows imported.")

if __name__ == "__main__":
    conn = sqlite3.connect(SQLITE_DB_PATH)
    for table_name, csv_file in TABLES:
        import_csv_to_sqlite(table_name, csv_file, conn)
    conn.close()
    print("Data import complete. Local SQLite database is ready.")
