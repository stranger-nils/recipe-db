#!/usr/bin/env python3
"""
Migration 006 — kanonisk ingredienskatalog.

Mål: ingredient-tabellen blir källan-till-sanning för vad som kan handlas.
Inga dubletter (koriander vs korriander), inga NULL-kategorier, varje rad har
en default_unit. Alias-mappning gör att vanliga felstavningar och synonymer
upplöses automatiskt vid skrivning.

Idempotent: bail:ar om ingredient redan har kolumnen `default_unit`.

Schemaändringar:
  ingredient:
    name              TEXT NOT NULL COLLATE NOCASE  (UNIQUE INDEX)
    grocery_category  TEXT NOT NULL CHECK (in ALLOWED_CATEGORIES)
    default_unit      TEXT NOT NULL                 (NY)
    kitchen_staple    INTEGER NOT NULL DEFAULT 0
    aliases           TEXT NOT NULL DEFAULT '[]'    (NY — JSON-array)
  -- notes REAL tas bort (var skräp från CSV-import)

Datatransform:
  - Slå ihop korriander → koriander, lök → gullök.
  - Radera 'vitlöksklyftor,' (0 användningar).
  - Döp om 'röd paprika)' → 'röd paprika'.
  - Fyll i grocery_category + default_unit för alla 100 ingredienser
    enligt CANONICAL nedan.
  - recipe_ingredient.ingredient_id pekas om till överlevande canonical id.
  - recipe_version.ingredients_json lämnas orörd (historisk snapshot).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path


ALLOWED_CATEGORIES = {
    "Frukt och grönt", "Färska örter", "Mejeri", "Kött", "Fågel", "Fläsk",
    "Fisk", "Kolhydrater", "Baljväxter", "Konserver", "Smaksättare",
    "Färdiga tillbehör", "Bageri", "Frys", "Alkohol", "Övrigt",
}

# Canonical katalog: name → (grocery_category, default_unit, kitchen_staple, [aliases])
# Namnet är exakt så det ska visas. Aliases är felstavningar/synonymer som ska
# resolvas till denna kanonisk-rad. Allt skrivs case-insensitivt.
CANONICAL: dict[str, tuple[str, str, int, list[str]]] = {
    # Frukt och grönt
    "avokado":        ("Frukt och grönt", "st", 0, []),
    "böngroddar":     ("Frukt och grönt", "g",  0, []),
    "citron":         ("Frukt och grönt", "st", 0, []),
    "daikon":         ("Frukt och grönt", "g",  0, []),
    "grön chili":     ("Frukt och grönt", "st", 0, []),
    "gullök":         ("Frukt och grönt", "st", 1, ["lök", "gul lök"]),
    "silverlök":      ("Frukt och grönt", "st", 0, []),
    "schalottenlök":  ("Frukt och grönt", "st", 0, []),
    "rödlök":         ("Frukt och grönt", "st", 0, []),
    "salladslök":     ("Frukt och grönt", "st", 0, []),
    "gurka":          ("Frukt och grönt", "st", 0, []),
    "ingefära":       ("Frukt och grönt", "g",  0, []),
    "lime":           ("Frukt och grönt", "st", 0, []),
    "morot":          ("Frukt och grönt", "st", 0, []),
    "palsternacka":   ("Frukt och grönt", "st", 0, []),
    "paprika":        ("Frukt och grönt", "st", 0, []),
    "potatis":        ("Frukt och grönt", "g",  0, []),
    "fast potatis":   ("Frukt och grönt", "g",  0, []),
    "mjölig potatis": ("Frukt och grönt", "g",  0, []),
    "röd paprika":    ("Frukt och grönt", "st", 0, ["röd paprika)"]),
    "rotselleri":     ("Frukt och grönt", "g",  0, []),
    "selleristjälk":  ("Frukt och grönt", "st", 0, []),
    "spetskål":       ("Frukt och grönt", "huvud", 0, []),
    "vitlök":         ("Frukt och grönt", "klyfta", 1, ["vitlöksklyfta", "vitlöksklyftor"]),

    # Färska örter
    "koriander":      ("Färska örter", "kruka", 0, ["korriander"]),
    "dill":           ("Färska örter", "knippe", 0, []),
    "persilja":       ("Färska örter", "knippe", 0, []),
    "färsk timjan":   ("Färska örter", "kvist", 0, []),
    "thaibasilika":   ("Färska örter", "kruka", 0, []),

    # Smaksättare (oljor, såser, kryddor, socker)
    "salt":              ("Smaksättare", "krm", 1, []),
    "flingsalt":         ("Smaksättare", "krm", 1, []),
    "havssalt":          ("Smaksättare", "nypa", 1, []),
    "svartpeppar":       ("Smaksättare", "krm", 1, []),
    "vitpeppar":         ("Smaksättare", "krm", 1, []),
    "olivolja":          ("Smaksättare", "msk", 1, []),
    "rapsolja":          ("Smaksättare", "msk", 1, []),
    "olja":              ("Smaksättare", "msk", 0, ["neutral olja"]),
    "sesamolja":         ("Smaksättare", "tsk", 1, ["rostad sesamolja"]),
    "ättika":            ("Smaksättare", "msk", 1, []),
    "soja":              ("Smaksättare", "msk", 1, []),
    "ljus soja":         ("Smaksättare", "msk", 1, []),
    "mörk soja":         ("Smaksättare", "tsk", 1, []),
    "fisksås":           ("Smaksättare", "msk", 0, []),
    "ostronsås":         ("Smaksättare", "msk", 1, []),
    "worcestershiresås": ("Smaksättare", "tsk", 0, []),
    "tabasco":           ("Smaksättare", "tsk", 0, []),
    "bulgogi-sås":       ("Smaksättare", "ml",  0, []),
    "gochujang":         ("Smaksättare", "msk", 0, []),
    "Lao Gan Ma chilikrisp": ("Smaksättare", "msk", 0, []),
    "röd currypasta":    ("Smaksättare", "msk", 0, []),
    "lingonsylt":        ("Smaksättare", "msk", 0, []),
    "tomatpuré":         ("Smaksättare", "msk", 1, []),
    "kycklingbuljong":   ("Smaksättare", "dl",  1, []),
    "viltfond":          ("Smaksättare", "msk", 0, []),
    "socker":            ("Smaksättare", "tsk", 1, ["strösocker"]),
    "farinsocker":       ("Smaksättare", "msk", 1, []),
    "palmsocker":        ("Smaksättare", "msk", 0, []),
    "paprikapulver":     ("Smaksättare", "tsk", 1, []),
    "rökt paprikapulver":("Smaksättare", "tsk", 0, []),
    "chiliflakes":       ("Smaksättare", "tsk", 0, []),
    "torkad chili":      ("Smaksättare", "st",  1, []),
    "torkad oregano":    ("Smaksättare", "tsk", 1, []),
    "herbes de provence":("Smaksättare", "tsk", 1, []),
    "garam masala":      ("Smaksättare", "tsk", 1, []),
    "gurkmeja":          ("Smaksättare", "tsk", 1, []),
    "muskotnöt":         ("Smaksättare", "nypa", 1, []),
    "korianderpulver":   ("Smaksättare", "tsk", 0, []),
    "spiskumminfrön":    ("Smaksättare", "tsk", 1, []),
    "fänkålsfrön":       ("Smaksättare", "tsk", 0, []),
    "bruna senapsfrön":  ("Smaksättare", "tsk", 0, []),
    "gula senapsfrön":   ("Smaksättare", "msk", 0, []),
    "dijonsenap":        ("Smaksättare", "tsk", 1, []),
    "skånsk grov senap": ("Smaksättare", "tsk", 0, []),
    "sesamfrön":         ("Smaksättare", "msk", 1, []),
    "lagerblad":         ("Smaksättare", "st",  1, []),
    "krossade enbär":    ("Smaksättare", "st",  0, []),
    "limeblad":          ("Smaksättare", "st",  0, []),
    "tacokrydda":        ("Smaksättare", "påse", 0, []),
    "majsstärkelse":     ("Smaksättare", "tsk", 1, []),
    "MSG":               ("Smaksättare", "nypa", 0, []),
    "risvinäger":        ("Smaksättare", "msk", 0, []),
    "ljus risvinäger":   ("Smaksättare", "ml", 0, []),
    "svart risvinäger":  ("Smaksättare", "tsk", 0, []),
    "kewpie-majonnäs":   ("Smaksättare", "msk", 0, []),

    # Mejeri
    "smör":             ("Mejeri", "g",   1, []),
    "mjölk":            ("Mejeri", "dl",  0, []),
    "vispgrädde":       ("Mejeri", "dl",  0, []),
    "gräddfil":         ("Mejeri", "dl",  0, []),
    "ghee":             ("Mejeri", "msk", 0, []),
    "parmesanost":      ("Mejeri", "g",   0, []),
    "parmesanrind":     ("Mejeri", "st",  0, []),
    "queso fresco":     ("Mejeri", "g",   0, []),
    "riven smakrik ost":("Mejeri", "dl",  0, []),
    "ägg":              ("Mejeri", "st",  1, ["äggula", "äggvita", "äggulor", "äggvitor"]),

    # Kött / Fågel / Fläsk / Fisk
    "blandning av malet kött": ("Kött", "g", 0, []),
    "nötfärs":         ("Kött", "g",  0, []),
    "flankstek":       ("Kött", "g",  0, []),
    "oxfilé":          ("Kött", "g",  0, []),
    "oxsvans":         ("Kött", "kg", 0, []),
    "märgben":         ("Kött", "kg", 0, []),
    "renskav":         ("Kött", "g",  0, []),
    "kycklinglår":     ("Fågel", "g", 0, []),
    "kycklinglårfilé": ("Fågel", "g", 0, []),
    "hel kyckling":    ("Fågel", "kg", 0, []),
    "pancetta":        ("Fläsk", "g", 0, []),
    "salsicca":        ("Fläsk", "g", 0, []),
    "isterband":       ("Fläsk", "st", 0, []),
    "fläskkotlett utan ben": ("Fläsk", "st", 0, []),
    "jätteräkor":      ("Fisk", "g", 0, []),

    # Kolhydrater / Baljväxter
    "basmatiris":         ("Kolhydrater", "dl", 1, []),
    "jasminris":          ("Kolhydrater", "dl", 1, []),
    "ris":                ("Kolhydrater", "dl", 1, []),
    "pappardelle":        ("Kolhydrater", "g",  0, []),
    "rigatoni":           ("Kolhydrater", "g",  0, []),
    "Hong Kong-äggnudlar":("Kolhydrater", "g",  0, []),
    "udon-nudlar":        ("Kolhydrater", "g",  0, []),
    "ströbröd":           ("Kolhydrater", "g",  0, []),
    "vetemjöl":           ("Kolhydrater", "g",  1, []),
    "röda linser":        ("Baljväxter",  "dl", 0, []),
    "svarta bönor":       ("Baljväxter",  "g",  0, []),
    "edamame i skida":    ("Baljväxter",  "g",  0, []),

    # Konserver
    "kimchi":                       ("Konserver", "burk", 0, []),
    "krossade tomater":             ("Konserver", "g",    0, []),
    "konserverade körsbärstomater": ("Konserver", "g",    0, []),
    "plommontomater":               ("Konserver", "g",    0, []),
    "passata":                      ("Konserver", "g",    0, []),
    "kokosgrädde":                  ("Konserver", "ml",   0, []),
    "majs":                         ("Konserver", "burk", 0, []),
    "picklade jalapeno":            ("Konserver", "burk", 0, []),
    "salsa":                        ("Konserver", "burk", 0, []),
    "inlagda rödbetor":             ("Konserver", "burk", 0, []),
    "cornichons":                   ("Konserver", "msk",  0, []),
    "kapris":                       ("Konserver", "msk",  0, []),

    # Frys
    "kantareller":   ("Frys", "g", 0, []),
    "frysta lingon": ("Frys", "g", 0, []),

    # Färdiga tillbehör
    "små majstortillas":  ("Färdiga tillbehör", "st", 0, []),
    "stora tortillabröd": ("Färdiga tillbehör", "förpackning", 0, []),
    "friterad lök":       ("Färdiga tillbehör", "msk", 1, []),
    "pommes frites":      ("Färdiga tillbehör", "portion", 0, []),

    # Alkohol
    "torrt vitt vin":     ("Alkohol", "dl", 0, ["torrt vitt eller rött vin"]),
    "shaoxing-vin":       ("Alkohol", "tsk", 0, []),

    # Övrigt
    "vatten":             ("Övrigt", "dl", 1, []),
}

# Old ingredient names som ska raderas helt (0 användningar, ren skräpdata).
DROP_NAMES = {"vitlöksklyftor,"}


def is_already_migrated(conn: sqlite3.Connection) -> bool:
    cols = {row[1] for row in conn.execute("PRAGMA table_info(ingredient)").fetchall()}
    return "default_unit" in cols


def build_alias_index() -> dict[str, str]:
    """name (lowercase) → canonical name."""
    idx: dict[str, str] = {}
    for canonical, (_, _, _, aliases) in CANONICAL.items():
        idx[canonical.lower()] = canonical
        for a in aliases:
            key = a.lower()
            if key in idx and idx[key] != canonical:
                raise RuntimeError(
                    f"Alias-konflikt: '{a}' pekar både på {idx[key]} och {canonical}"
                )
            idx[key] = canonical
    return idx


def validate_categories() -> None:
    for name, (cat, unit, _, _) in CANONICAL.items():
        if cat not in ALLOWED_CATEGORIES:
            raise RuntimeError(f"{name}: okänd kategori '{cat}'")
        if not unit.strip():
            raise RuntimeError(f"{name}: tom default_unit")


def migrate(conn: sqlite3.Connection) -> None:
    validate_categories()
    alias_idx = build_alias_index()

    # Läs nuvarande ingredienser.
    old_rows = conn.execute(
        "SELECT id, name, kitchen_staple FROM ingredient"
    ).fetchall()

    # 1) Mappa varje gammal id → kanoniskt namn (eller None om ska raderas).
    remap: dict[int, str | None] = {}  # old_id → canonical_name
    unknown: list[tuple[int, str]] = []
    for old_id, old_name, _ in old_rows:
        name_norm = (old_name or "").strip()
        if name_norm in DROP_NAMES or name_norm.lower() in {d.lower() for d in DROP_NAMES}:
            remap[old_id] = None
            continue
        canonical = alias_idx.get(name_norm.lower())
        if canonical is None:
            unknown.append((old_id, old_name))
        else:
            remap[old_id] = canonical

    if unknown:
        msg = "\n".join(f"  id={i} name={n!r}" for i, n in unknown)
        raise RuntimeError(
            "Följande ingredienser saknar mappning i CANONICAL/DROP_NAMES:\n" + msg
        )

    # 2) Refusera att radera ingredienser som faktiskt används.
    used_to_drop = []
    for old_id, canonical in remap.items():
        if canonical is None:
            count = conn.execute(
                "SELECT COUNT(*) FROM recipe_ingredient WHERE ingredient_id=?",
                (old_id,),
            ).fetchone()[0]
            if count:
                used_to_drop.append((old_id, count))
    if used_to_drop:
        raise RuntimeError(
            f"DROP_NAMES innehåller använda ingredienser: {used_to_drop}"
        )

    # 3) Bestäm överlevande id för varje canonical: min(old_id) bland alla som
    #    pekar på den. Canonicals som inte finns i DB:n alls får nytt id.
    used_old_ids: dict[str, list[int]] = {}
    for old_id, canonical in remap.items():
        if canonical is None:
            continue
        used_old_ids.setdefault(canonical, []).append(old_id)

    surviving_id: dict[str, int] = {}
    next_new_id = (
        conn.execute("SELECT COALESCE(MAX(id), 0) FROM ingredient").fetchone()[0] + 1
    )
    for canonical in CANONICAL:
        if canonical in used_old_ids:
            surviving_id[canonical] = min(used_old_ids[canonical])
        else:
            surviving_id[canonical] = next_new_id
            next_new_id += 1

    # 4) Bygg id-remap för recipe_ingredient (gammalt id → överlevande id).
    ri_remap = {
        old_id: surviving_id[canonical]
        for old_id, canonical in remap.items()
        if canonical is not None
    }

    # 5) Skapa nytt ingredient-schema och fyll det.
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("BEGIN")

    conn.execute("DROP VIEW IF EXISTS recipe_with_ingredients")

    cat_check = " OR ".join(
        f"grocery_category = '{c}'" for c in sorted(ALLOWED_CATEGORIES)
    )
    conn.execute(f"""
        CREATE TABLE ingredient_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE
                CHECK (length(TRIM(name)) > 0),
            grocery_category TEXT NOT NULL
                CHECK ({cat_check}),
            default_unit TEXT NOT NULL
                CHECK (length(TRIM(default_unit)) > 0),
            kitchen_staple INTEGER NOT NULL DEFAULT 0
                CHECK (kitchen_staple IN (0, 1)),
            aliases TEXT NOT NULL DEFAULT '[]'
        )
    """)

    # Behåll kitchen_staple-värdet från gamla raden där det är 1, annars
    # värdet i CANONICAL.
    old_staple_by_canonical: dict[str, int] = {}
    for old_id, old_name, old_staple in old_rows:
        canonical = remap.get(old_id)
        if canonical is None:
            continue
        if old_staple:
            old_staple_by_canonical[canonical] = 1

    for canonical, (cat, unit, default_staple, aliases) in CANONICAL.items():
        new_id = surviving_id[canonical]
        staple = old_staple_by_canonical.get(canonical, default_staple)
        conn.execute(
            """
            INSERT INTO ingredient_new (id, name, grocery_category, default_unit,
                                        kitchen_staple, aliases)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (new_id, canonical, cat, unit, staple, json.dumps(aliases, ensure_ascii=False)),
        )

    # 6) Skriv om recipe_ingredient.ingredient_id.
    for old_id, new_id in ri_remap.items():
        if old_id == new_id:
            continue
        conn.execute(
            "UPDATE recipe_ingredient SET ingredient_id=? WHERE ingredient_id=?",
            (new_id, old_id),
        )

    # 7) Svänga in nya tabellen.
    conn.execute("DROP TABLE ingredient")
    conn.execute("ALTER TABLE ingredient_new RENAME TO ingredient")

    conn.execute(
        "CREATE UNIQUE INDEX idx_ingredient_name "
        "ON ingredient(name COLLATE NOCASE)"
    )

    # Reseed sqlite_sequence.
    max_id = conn.execute("SELECT COALESCE(MAX(id), 0) FROM ingredient").fetchone()[0]
    conn.execute("DELETE FROM sqlite_sequence WHERE name = 'ingredient'")
    conn.execute(
        "INSERT INTO sqlite_sequence(name, seq) VALUES (?, ?)",
        ("ingredient", max_id),
    )

    # 8) Bygg om VIEW med nya kolumnerna.
    conn.execute("""
        CREATE VIEW recipe_with_ingredients AS
        SELECT
            r.id AS recipe_id, r.title, r.description, r.instructions,
            r.notes, r.tags, r.type, r.kitchen,
            i.id AS ingredient_id, i.name AS ingredient_name,
            i.grocery_category, i.default_unit, i.kitchen_staple, i.aliases,
            ri.amount, ri.unit, ri.note AS ingredient_note
        FROM recipe r
        LEFT JOIN recipe_ingredient ri ON ri.recipe_id = r.id
        LEFT JOIN ingredient i ON i.id = ri.ingredient_id
    """)

    conn.execute("COMMIT")
    conn.execute("PRAGMA foreign_keys = ON")

    violations = conn.execute("PRAGMA foreign_key_check").fetchall()
    if violations:
        raise RuntimeError(f"FK-överträdelser efter migrering: {violations}")


def main() -> int:
    db_path = Path(sys.argv[1] if len(sys.argv) > 1 else "recipe.db")
    if not db_path.exists():
        print(f"✗ DB not found: {db_path}", file=sys.stderr)
        return 1

    conn = sqlite3.connect(str(db_path), isolation_level=None)

    if is_already_migrated(conn):
        print("✓ Already migrated (ingredient.default_unit finns). No-op.")
        return 0

    before_ing = conn.execute("SELECT COUNT(*) FROM ingredient").fetchone()[0]
    before_ri = conn.execute("SELECT COUNT(*) FROM recipe_ingredient").fetchone()[0]
    print(f"--- BEFORE ({db_path}) ---")
    print(f"  ingredient: {before_ing}")
    print(f"  recipe_ingredient: {before_ri}")

    try:
        migrate(conn)
    except Exception as e:
        try:
            conn.execute("ROLLBACK")
        except sqlite3.OperationalError:
            pass
        print(f"✗ Migration failed: {e}", file=sys.stderr)
        return 1

    after_ing = conn.execute("SELECT COUNT(*) FROM ingredient").fetchone()[0]
    after_ri = conn.execute("SELECT COUNT(*) FROM recipe_ingredient").fetchone()[0]
    print(f"\n--- AFTER ---")
    print(f"  ingredient: {after_ing} (var {before_ing})")
    print(f"  recipe_ingredient: {after_ri}{' ✗ ÄNDRAT' if after_ri != before_ri else ''}")

    if after_ri != before_ri:
        print("\n✗ recipe_ingredient ändrade antal — undersök!", file=sys.stderr)
        return 2

    # Verifiera invarianter.
    nulls = conn.execute("""
        SELECT COUNT(*) FROM ingredient
        WHERE grocery_category IS NULL OR default_unit IS NULL
    """).fetchone()[0]
    if nulls:
        print(f"✗ {nulls} ingredient-rader har NULL-fält", file=sys.stderr)
        return 3

    print("\n✓ Migration successful — katalogen är canonical.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
