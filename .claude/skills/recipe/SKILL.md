---
name: recipe
description: "Brainstorma receptidéer, föreslå kompletta recept på svenska och spara nya recept till SQLite-databasen. Triggas när användaren vill ha receptförslag, matinspiration, middagstips, eller spara ett nytt recept. Nyckelord: recept, middag, mat, laga, ingredienser, spara recept, push, brainstorm. För att redigera/uppdatera/justera ett befintligt recept — använd skillen edit-recipe istället."
---

# Recipe Skill — Receptidéer & Nya recept

## Profil
Läs `.claude/cowork-instructions.md` om den finns. Den definierar ton och samarbetsstil. Följ den.

## Syfte
Hjälp användaren brainstorma receptidéer och spara nya recept i databasen. Visa preview i chatten, skriv till databasen först när användaren säger **"push"**.

> **Edits hanteras av en separat skill.** Om användaren vill ändra något i ett *redan publicerat* recept — efterkok-reflektion, ny version, justering — invokera `edit-recipe`-skillen istället. Den här skillen handlar om **nya recept**.

## Språk
Alla recept, ingredienser och instruktioner ska vara på **svenska**.

## Miljö-detektion — Två lägen

Skillen körs i två miljöer med olika capabilities:

- **Claude Code-läge** (terminal på Macbook): Har direkt SSH-access till VPS:en (`ssh minvps`). Skriver direkt till auktoritativ databas på VPS.
- **Cowork-läge** (desktop-app, sandboxed): Har ingen nätverksaccess till VPS. Skriver "pending commits" till fil — Claude Code applicerar dem senare.

**Detektera vid sessionsstart:**

```bash
ssh -o ConnectTimeout=5 -o BatchMode=yes minvps 'echo ok' 2>/dev/null
```

- Exit 0 → **Claude Code-läge**.
- Annat → **Cowork-läge**.

Kommunicera tydligt med användaren i början av en arbetsflödes-sekvens vilket läge som är aktivt, särskilt vid push ("sparad direkt till VPS" vs "sparad som pending commit — växla till Claude Code för att applicera").

## ⚠️ Vanliga fallgropar — läs INNAN du skriver pending-commit

1. **Fältnamn i pending-commit JSON är `type` och `kitchen`** — INTE `section`/`menu`. Det gamla schemat döptes om i migration 005. Använder du `section`/`menu` kommer recepten sparas med NULL i kategorisering.
2. **Varje ingrediens MÅSTE ha `default_unit`** i JSON (inte bara `unit`). `ingredient.default_unit` är NOT NULL i DB:n — saknas det rejectas inserten för alla *nya* ingredienser.
3. **`kitchen` är ren text utan emoji.** Skriv `"Mexikanskt"`, inte `"🌮 Mexikanskt"`.
4. **`type` är ett av**: `förrätt`, `huvudrätt`, `sidorätt`, `komponent`, `efterrätt`. Inte fritext som `"Tacos"` eller `"Salsa"` (det hör hemma i `tags`).

Se det fullständiga JSON-schemat längre ner — kopiera från det, inte från minnet.

## Databas

### Schema
```sql
recipe (id, title, description, instructions, notes, tags, type, kitchen)
ingredient (id, name, grocery_category, default_unit, kitchen_staple, aliases)
recipe_ingredient (recipe_id, ingredient_id, amount, unit, note)
recipe_version (id, recipe_id, version_number, title, description, instructions, notes,
                tags, type, kitchen, ingredients_json, changed_at, changed_by, change_note)
```

`ingredient` är en **kanonisk katalog** (migration 006). Varje rad måste ha:
- `name` (UNIQUE COLLATE NOCASE)
- `grocery_category` (NOT NULL, måste vara från listan nedan)
- `default_unit` (NOT NULL — t.ex. `g`, `dl`, `msk`, `tsk`, `st`, `klyfta`, `kruka`, `knippe`, `burk`)
- `kitchen_staple` (0/1)
- `aliases` (JSON-array, t.ex. `["korriander", "coriander"]`)

Inga dubletter tillåts. Felstavningar/synonymer går i `aliases` på den kanoniska raden.

### Auktoritativ DB-path (Claude Code-läge)

På VPS: `/opt/recipe-db/data/recipe.db`. Nås via `ssh minvps`.

För en snabb läsning från VPS:
```bash
ssh minvps "sqlite3 /opt/recipe-db/data/recipe.db 'SELECT ...'"
```

För en transaktion (bygg SQL som text, pipea in):
```bash
cat sql-kommandon.sql | ssh minvps 'sqlite3 /opt/recipe-db/data/recipe.db'
```

Viktigt: inkapsla alla skrivoperationer i `BEGIN; ... COMMIT;` (eller `ROLLBACK` vid fel).

### Lokal snapshot (Cowork-läge)

I Cowork-läge finns en lokal `recipe.db` i projektroten som en **read-only snapshot** av VPS-databasen. Skillen använder den för:
- Ingrediens-matching (best-effort: "denna ingrediens finns troligen redan")
- Preview-data (titlar av existerande recept etc.)

Skillen **skriver aldrig** till lokal `recipe.db` i Cowork-läge. All data skapas som pending-commit-JSON.

**Hitta lokal DB dynamiskt:**
```python
import glob
hits = glob.glob("/sessions/*/mnt/recipe-db/recipe.db")
db_path = hits[0] if hits else None
```

Om snapshoten saknas/är tom: arbeta vidare med anteckning till användaren ("kunde inte läsa lokal snapshot — ingrediens-matching blir best effort; gör en `scp` från VPS om du vill ha aktuell data").

### Läs-mönster (gäller båda lägen för lokal snapshot)

Det monterade filsystemet (Cowork) stöder inte SQLites journal-mode vid läsning med öppna handles. Använd copy-to-temp vid läsning av lokal snapshot:

```python
import sqlite3, shutil, tempfile, os

def read_snapshot(db_path):
    tmp = tempfile.mktemp(suffix='.db')
    shutil.copy(db_path, tmp)
    conn = sqlite3.connect(tmp)
    return conn, tmp  # ansvar att stänga conn + radera tmp
```

### Tillåtna grocery_category-värden (fast lista, CHECK constraint i DB)
`Frukt och grönt`, `Färska örter`, `Mejeri`, `Kött`, `Fågel`, `Fläsk`, `Fisk`,
`Kolhydrater`, `Baljväxter`, `Konserver`, `Smaksättare`, `Färdiga tillbehör`,
`Bageri`, `Frys`, `Alkohol`, `Övrigt`.

Använd **exakt** dessa strängar — DB:n rejectar allt annat.

### Ingrediens-canonicalization — VIKTIGT

Ingredient-tabellen tillåter inga dubletter. Innan du föreslår en ingrediens:

1. **Slå upp i lokal snapshot / VPS** mot både `name` (NOCASE) **och** `aliases`-arrayen.
2. **Matchar något** → använd det kanoniska namnet exakt som det står i DB. Inte din egen variant.
3. **Granularitet**: katalogen ska bara innehålla saker som **handlas separat i butik**. Exempel:
   - `ägg` finns. `äggula`/`äggvita` finns **inte** — det är samma inköp. Skriv `ägg` som ingrediens och lägg "endast gulor" i `recipe_ingredient.note`.
   - `gullök` och `silverlök` finns separat (olika inköp).
   - `vitlök` finns (default_unit `klyfta`). Skriv aldrig `vitlöksklyfta` som egen rad — det är ett alias.
4. **Ny ingrediens behövs** → du måste alltid ange `grocery_category` (från listan ovan) **och** `default_unit` i pending-commit/preview. Annars rejectar DB:n (CHECK + NOT NULL).

Lookup-mönster (Python, mot lokal snapshot):
```python
def resolve_ingredient(conn, query):
    """Returnerar (id, canonical_name) eller (None, None)."""
    row = conn.execute(
        "SELECT id, name FROM ingredient WHERE name = ? COLLATE NOCASE",
        (query,),
    ).fetchone()
    if row:
        return row
    # Alias-lookup
    import json
    for rid, name, aliases_json in conn.execute(
        "SELECT id, name, aliases FROM ingredient"
    ):
        if query.lower() in [a.lower() for a in json.loads(aliases_json or '[]')]:
            return (rid, name)
    return (None, None)
```

### Befintliga tags-konventioner
Kommaseparerade, gemener: t.ex. `italiensk,pasta` eller `stark, nötkött`.

## Arbetsflöde — Nytt recept

### Steg 1 — Brainstorming
Ge **kompletta** receptförslag direkt (titel, beskrivning, ingredienser med mängd/enhet, numrerade instruktioner). Anpassa efter användarens önskemål. Var kreativ men praktisk — rätter man faktiskt vill laga hemma.

### Steg 2 — Commit preview

När användaren gillar ett recept och vill spara:

1. **Läs snapshot** (Cowork) eller **läs VPS** (Claude Code) för ingrediens-matching.
2. **Föreslå kategorisering**: `tags`, `type` (förrätt/huvudrätt/sidorätt/komponent/efterrätt), `kitchen` (kök, t.ex. Italienskt, Mexikanskt).
3. **Visa preview:**

```
📝 COMMIT PREVIEW — NYTT RECEPT
═══════════════════════════════════

📖 Recept: [titel]
   tags: [tags]
   type: [type]
   kitchen: [kitchen]

🥕 Ingredienser:
   - [kanoniskt namn] — [mängd] [enhet]   (existerande)
   - [nytt namn] — [mängd] [enhet]        (NY: kategori=X, default_unit=Y)
   - ...

═══════════════════════════════════
Säg "push" för att spara,
eller ge feedback för att justera.
```

I Cowork-läge: visa **inte** numeriska ID:n (de tilldelas vid push mot VPS). I Claude Code-läge: visa preliminärt ID (MAX(id)+1 från VPS).

### Steg 3 — Push

**Claude Code-läge:** Direkt mot VPS.

1. Via SSH, kör en transaktion mot `/opt/recipe-db/data/recipe.db`:
   - MAX(id) + 1 för nytt recept.
   - För varje ingrediens: `LOWER(name)`-matcha → återanvänd ID eller skapa ny.
   - INSERT i `recipe`.
   - INSERT i `recipe_ingredient`.
   - INSERT i `recipe_version` med `version_number = 1`, `changed_by = 'chat'`, `changed_at = <ISO-timestamp>`, `ingredients_json = <serialiserad lista>`.
2. Bekräfta:

```
✅ Sparat på VPS! [titel] (id: [id], version: 1)
   - [X] ingredienser kopplade ([Y] nya skapade)
```

**Cowork-läge:** Skriv pending-commit.

1. Bygg commit-objekt (schema nedan), skriv till `.claude/pending-commits/<ISO-timestamp>_<slug>.json`.
2. Bekräfta:

```
📦 Pending commit skapad: [filnamn]
   Öppna Claude Code i projektmappen och säg "apply pending"
   för att skriva till VPS-databasen.
```

## "apply pending" (endast Claude Code-läge)

När användaren säger **"apply pending"** eller **"push pending"**:

1. `ls .claude/pending-commits/` — om tomt, rapportera det.
2. Visa batch-preview: en rad per commit med filnamn, operation, titel.
3. Vid bekräftelse, för varje fil:
   - Parsa JSON.
   - Kör push-flödet ovan (just nu bara `operation: "create"` — edits hanteras av `edit-recipe`-skillen via HTTP-API och ligger inte i pending-kön).
   - Vid success: `mv <fil> .claude/applied-commits/`.
   - Vid error: rapportera, låt filen ligga kvar.
4. Rapportera slutresultat:

```
✅ Applicerat [N] pending commits
⚠️  [M] kvar i pending (se fel ovan)
```

## Pending-commit JSON-schema

```json
{
  "schema_version": "1",
  "operation": "create",
  "title": "Snabbtacos med halloumi",
  "description": "...",
  "instructions": "1. ...\n2. ...",
  "notes": null,
  "tags": "vegetariskt,tacos",
  "type": "huvudrätt",
  "kitchen": "Mexikanskt",
  "ingredients": [
    {
      "name": "halloumi",
      "amount": "250",
      "unit": "g",
      "note": "",
      "kitchen_staple": 0,
      "grocery_category": "Mejeri",
      "default_unit": "g"
    }
  ],
  "created_at": "2026-04-19T22:30:00Z",
  "created_by": "cowork"
}
```

Filnamn: `.claude/pending-commits/<YYYY-MM-DDTHH-MM-SSZ>_<slug>.json`. `slug` = lowercase, bindestreck istället för mellanslag, ASCII-safe.

> **Notera:** `operation: "update"` används inte längre i pending-commit-flödet — edits hanteras av `edit-recipe`-skillen via HTTP-API. Den här skillen ska bara producera `create`-commits.

## Viktiga regler

- **ID-hantering**: Läs alltid MAX(id) från auktoritativ DB (VPS i Claude Code-läge) innan insert. Aldrig hårdkodade ID:n.
- **Ingrediensmatchning**: NOCASE + alias-lookup. Använd alltid kanoniskt namn från DB:n, aldrig din egen stavning om det finns en träff.
- **Nya ingredienser**: kräver `grocery_category` (från listan) + `default_unit` + `kitchen_staple` (1 för skafferisaker som salt/peppar/olja, annars 0). Saknas något → DB:n rejectar med CHECK/NOT NULL.
- **Granularitet**: bara det som inhandlas separat. `äggula` ≠ ny rad. `gullök` vs `silverlök` = separata rader.
- **Instruktioner**: Numrerade steg, separerade med newlines.
- **notes**: NULL om inget speciellt.
- **Transaktioner**: Alla skrivningar inom `BEGIN; ... COMMIT;` (ROLLBACK vid fel).
- **Visa alltid preview innan push** — aldrig direkt till DB utan bekräftelse.
- **Versionshistorik**: Varje push (nytt eller edit) loggar en rad i `recipe_version`.
- **Lokal snapshot skrivs aldrig**: I Cowork-läge är lokal `recipe.db` strikt read-only. All skrivning går till pending-commit-fil.
- **Edits → annan skill**: Om användaren vill ändra ett befintligt recept, säg "Det här är `edit-recipe`-territorium — invokera den" istället för att gå vidare.
