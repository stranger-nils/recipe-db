---
name: recipe
description: "Brainstorma receptidéer, föreslå kompletta recept på svenska och spara nya recept till SQLite-databasen. Triggas när användaren vill ha receptförslag, matinspiration, middagstips, eller spara ett nytt recept. Nyckelord: recept, middag, mat, laga, ingredienser, spara recept, push, brainstorm. För att redigera/uppdatera/justera ett befintligt recept — använd skillen edit-recipe istället."
---

<!-- SKILL_VERSION: 2026-11-15 -->

## ⚠️ Versionskontroll — gör detta först

Den här skillen finns i två kopior som uppdateras via **olika kanaler** och glider isär tyst:

- **Repot**: `recipe-db/.claude/skills/recipe/SKILL.md` — source of truth, versionerad i git.
- **Claude-kontot** (Customize → Skills) — det är den kopian Cowork laddar, och den uppdateras **bara** genom manuell uppladdning.

Kontrollera därför alltid vid start, innan du gör något annat:

1. Läs `SKILL_VERSION`-raden överst i den här filen — det är kopian du kör just nu.
2. Är `recipe-db` åtkomlig (Cowork: ansluten mapp, Claude Code: repo-roten)? Läs `SKILL_VERSION` överst i `.claude/skills/recipe/SKILL.md`.
3. **Är repot nyare** → följ repo-filen i den här sessionen, och säg det rakt ut till användaren:
   > "Kontots skill-kopia är daterad `<kontots datum>`, repot har `<repots datum>`. Jag följer repo-versionen. Ladda upp den nya filen under Customize → Skills så försvinner glappet."
4. Går repot inte att läsa → nämn i en mening att versionskontrollen inte kunde göras.

Hoppa aldrig över steget. Det kostar två filläsningar och är enda skyddet mot att köra en månadsgammal instruktion utan att märka det.

# Recipe Skill — Receptidéer & Nya recept

## Profil
Läs `.claude/cowork-instructions.md` om den finns. Den definierar ton och samarbetsstil. Följ den.

## Syfte
Hjälp användaren brainstorma receptidéer och spara nya recept i databasen. Visa preview i chatten, skriv till databasen först när användaren säger **"push"**.

> **Edits hanteras av en separat skill.** Om användaren vill ändra något i ett *redan publicerat* recept — efterkok-reflektion, ny version, justering — invokera `edit-recipe`-skillen istället. Den här skillen handlar om **nya recept**.

## Språk
Alla recept, ingredienser och instruktioner ska vara på **svenska**.

## Var databasen bor

Receptdatabasen ligger på **Raspberry Pi:n `nils-rpi`**. Flask-appen körs där i en container, och samma databas används av OpenClaw-agenten **Iris** — det du sparar här syns för henne och tvärtom.

- API: `http://100.127.88.96:5001` (Tailscale) — på hemma-LAN även `http://192.168.1.82:5001`.
- **Skriv aldrig direkt till SQLite** — inte till Pi:ns fil, inte till någon lokal `recipe.db`. Allt går via API:t.
- Ingen SSH till Pi:n behövs eller finns.
- `https://recipedb.cloud` är den **gamla VPS:en**, frusen vid recept-id 41. Använd den aldrig.
- Nya recept kräver ingen deploy.

## Spara-väg — HTTP-API, pending-commit som reserv

Nya recept sparas via **HTTP-API:t** (`POST /api/recipe`) — samma mellanlager som `edit-recipe` och Iris använder. Det fungerar i både Cowork och Claude Code och skapar receptet, kopplar ingredienser och loggar `recipe_version` v1 i en transaktion.

**Välj väg vid push:**

1. Sourca `.claude/.env` och kontrollera `RECIPE_API_URL` + `RECIPE_API_TOKEN` (se Konfiguration nedan).
2. Båda satta och API:t svarar → **HTTP-API:t** (Steg 3a). Normalfallet.
3. Saknas konfig, eller API:t går inte att nå → **pending-commit** (Steg 3b). Filen appliceras senare via API:t med `scripts/skill_remote_commit.py`.

Säg tydligt vid push vilken väg som användes ("sparad i receptdatabasen på Pi:n via API" vs "sparad som pending commit — appliceras när API:t går att nå").

## Konfiguration — `.claude/.env`

```
RECIPE_API_URL=http://100.127.88.96:5001
RECIPE_API_TOKEN=<samma som RECIPE_API_TOKEN i recipe-db/.env på Pi:n>
```

**Skriv aldrig ut tokenen** — inte i chatten, inte i loggar, inte i kommandon som ekar den. Läs den ur filen vid varje anrop. Svarar API:t 401 med tokenen i `.claude/.env`: säg det och be Nils om rätt token (den finns i `recipe-db/.env` på Pi:n). Det finns en `.claude/.env.example` att kopiera.

**Sourca .env i bash så här:**

```bash
set -a
# Cowork-sandbox-path:
[ -f /sessions/*/mnt/recipe-db/.claude/.env ] && \
  source /sessions/*/mnt/recipe-db/.claude/.env 2>/dev/null
# Claude Code (Mac):
ENV_FILE="$(ls -d "$HOME"/recipe-db/.claude/.env 2>/dev/null | head -1)"
[ -n "$ENV_FILE" ] && source "$ENV_FILE" 2>/dev/null
set +a
[ -n "$RECIPE_API_URL" ] && [ -n "$RECIPE_API_TOKEN" ] || echo "NO_API_CONFIG"
```

## Receptets innehåll — husregler (gemensamma med Iris)

Varje recept som föreslås och sparas ska följa detta:

1. **Komplett och på svenska**: titel, kort beskrivning, ingredienser med mängd + enhet, instruktioner, `notes`, kategorisering.
2. **4 portioner** som standard, om inte Nils säger annat. Ange portionerna i beskrivningen eller i första steget.
3. **Numrerade steg** (`1. …\n2. …`) med **temperatur och tid** där det är relevant ("Rosta i ugnen på 225 °C i 20–25 min", "Bryn på hög värme 2–3 min per sida").
4. **`notes`** samlar tips, vetenskap och alternativ i den här formen (samma som Iris recept):
   ```
   💡 Proffstips:
   - 1–3 konkreta tips
   🔬 Vetenskap:
   - (valfritt) varför tekniken fungerar
   🎨 Alternativ:
   - 1–3 alternativ (byten, varianter, vegetariskt)
   ```
   Proffstips (1–3) och alternativ (1–3) är obligatoriska; vetenskap är valfritt.
5. **Ingredienser** matchas mot ingredient-tabellen (`name` + `aliases`, case-insensitive) och får sitt **kanoniska namn**. En ny ingrediens kräver `grocery_category` (fast lista nedan) och `default_unit`.
6. **`kitchen`** har alltid emoji-prefix (`🇮🇹 Italienskt`). **`tags`** skrivs med gemener.
7. **`type`** är en av: `förrätt`, `huvudrätt`, `sidorätt`, `komponent`, `efterrätt` (gemener). Rättstypen (tacos, wok, pasta, soppa …) hör hemma i `tags`.
8. **Visa alltid en preview** och spara först när Nils säger **"push"**.
9. Vid `400` med `missing_fields`: rätta och POSTa igen.

## ⚠️ Vanliga fallgropar — läs INNAN du sparar

Gäller **både** API-body och pending-commit JSON:

1. **Fältnamnen är `type` och `kitchen`** — INTE `section`/`menu` (döptes om i migration 005). Fel namn → NULL i kategoriseringen.
2. **Varje *ny* ingrediens MÅSTE ha `default_unit`** (inte bara `unit`) **och** `grocery_category`. Annars 400 med `missing_fields`.
3. **`kitchen` sätts aldrig ur minnet** — hämta befintliga värden live via API:t (se "Kategoriseringskonventioner") och kopiera därifrån.
4. **`type` är enum-värdet med gemener**, inte en rättstyp. Databasen innehåller äldre värden som `Huvudrätt`, `Tacos`, `Wok` — återanvänd dem inte.

## Databas

### Schema
```sql
recipe (id, title, description, instructions, notes, tags, type, kitchen)
ingredient (id, name, grocery_category, default_unit, kitchen_staple, aliases)
recipe_ingredient (recipe_id, ingredient_id, amount, unit, note)
recipe_version (id, recipe_id, version_number, title, description, instructions, notes,
                tags, type, kitchen, ingredients_json, changed_at, changed_by, change_note)
```

`ingredient` är en **kanonisk katalog** (migration 006). Varje rad har:
- `name` (UNIQUE COLLATE NOCASE)
- `grocery_category` (NOT NULL, från listan nedan)
- `default_unit` (NOT NULL — t.ex. `g`, `dl`, `msk`, `tsk`, `st`, `klyfta`, `kruka`, `knippe`, `burk`)
- `kitchen_staple` (0/1)
- `aliases` (JSON-array, t.ex. `["korriander", "coriander"]`)

Inga dubletter tillåts. Felstavningar/synonymer går i `aliases` på den kanoniska raden.

Databasfilen ligger på Pi:n och nås **bara via API:t**. En eventuell lokal `recipe.db` i repot är en gammal kopia från VPS-tiden — använd den inte.

### Tillåtna grocery_category-värden (fast lista, CHECK constraint i DB)
`Frukt och grönt`, `Färska örter`, `Mejeri`, `Kött`, `Fågel`, `Fläsk`, `Fisk`,
`Kolhydrater`, `Baljväxter`, `Konserver`, `Smaksättare`, `Färdiga tillbehör`,
`Bageri`, `Frys`, `Alkohol`, `Övrigt`.

Använd **exakt** dessa strängar — DB:n rejectar allt annat.

### Ingrediens-canonicalization — VIKTIGT

1. **Bygg ingredienskatalogen via API:t** (kodblocket nedan). Det finns ingen `/api/ingredient`-endpoint, så katalogen härleds ur alla recept — `GET /api/recipe/<id>` returnerar per ingrediens `name`, `aliases`, `grocery_category`, `default_unit`, `kitchen_staple`.
2. **Matcha** mot `name` och `aliases`, case-insensitive. Träff → använd det kanoniska `name` exakt.
3. **Granularitet**: katalogen innehåller bara saker som **handlas separat i butik**:
   - `ägg` finns. `äggula`/`äggvita` finns **inte** — skriv `ägg` och lägg "endast gulor" i `note`.
   - `gullök` och `silverlök` finns separat (olika inköp).
   - `vitlök` finns (default_unit `klyfta`). Skriv aldrig `vitlöksklyfta` som egen rad — det är ett alias.
4. **Ny ingrediens** → ange alltid `grocery_category` (från listan) **och** `default_unit` (och `kitchen_staple`). Markera den `(NY)` i previewen — men bara om den saknas i katalogen från API:t.

```python
import json, os, urllib.request
base, tok = os.environ['RECIPE_API_URL'], os.environ['RECIPE_API_TOKEN']

def _get(path):
    req = urllib.request.Request(base + path, headers={'Authorization': 'Bearer ' + tok})
    return json.load(urllib.request.urlopen(req, timeout=15))

def ingredient_catalog():
    """{lowercase namn eller alias: kanonisk ingrediens-dict}, härlett ur alla recept."""
    rows = _get('/api/recipe/search?q=')['results']
    cat = {}
    for r in rows:
        for ing in _get('/api/recipe/%d' % r['id']).get('ingredients') or []:
            if not ing.get('name'):
                continue
            for key in [ing['name'], *(ing.get('aliases') or [])]:
                cat.setdefault(key.lower(), ing)
    return cat

def resolve(cat, name):
    """Returnerar kanoniskt namn eller None (= ny ingrediens)."""
    hit = cat.get(name.lower())
    return hit['name'] if hit else None
```

### Kategoriseringskonventioner (kitchen, type, tags)

Hämta befintliga värden live innan varje preview:

```bash
curl -sS -H "Authorization: Bearer $RECIPE_API_TOKEN" \
  "$RECIPE_API_URL/api/recipe/search?q=" \
| python3 -c "
import json, sys
rows = json.load(sys.stdin)['results']
print('KITCHEN:', sorted({r['kitchen'] for r in rows if r['kitchen']}))
print('TYPE:',    sorted({r['type']    for r in rows if r['type']}))
"
```

(`q=` tomt → alla recept med `id`, `title`, `kitchen`, `type`.)

**`kitchen`, i ordning:**

1. **Exakt emoji-variant finns** (t.ex. `🇮🇹 Italienskt`) → använd strängen tecken för tecken, kopierad från utdatan.
2. **Bara en variant utan emoji finns** (legacy) → bilda emoji-varianten av samma text och markera i previewen att den är normaliserad.
3. **Köket finns inte** → nytt värde: **emoji + mellanslag + text med inledande versal** (flagga för nationella kök, annars passande emoji: `🍜 Asiatiskt`, `🍲 Grunder`). Markera `(NYTT kök)`.

`kitchen` utan emoji är alltid fel.

**`type`**: exakt ett av `förrätt`, `huvudrätt`, `sidorätt`, `komponent`, `efterrätt`. Gemener, ingen emoji. (En sås, fond eller dressing som används i andra rätter = `komponent`.)

**`tags`**: kommaseparerade, gemener, ingen emoji. Här hamnar rättstyp, råvara och karaktär: `tacos,mexikanskt,nötkött,stark`.

## Arbetsflöde — Nytt recept

### Steg 1 — Brainstorming
Ge **kompletta** receptförslag enligt husreglerna ovan (4 portioner, numrerade steg med temp/tid, proffstips + alternativ). Anpassa efter önskemål. Kreativt men praktiskt — rätter man faktiskt vill laga hemma.

### Steg 2 — Commit preview

När Nils gillar ett recept och vill spara:

1. **Bygg ingredienskatalogen** via API:t (`ingredient_catalog()`) och matcha varje ingrediens.
2. **Hämta befintliga `kitchen`-värden** med query-steget ovan.
3. **Föreslå kategorisering**: `tags` (gemener), `type` (enum), `kitchen` (befintlig emoji-variant, normaliserad eller ny).
4. **Visa preview:**

```
📝 COMMIT PREVIEW — NYTT RECEPT
═══════════════════════════════════

📖 Recept: [titel]
   [beskrivning]
   Portioner: 4
   tags: [tags]
   type: [type]
   kitchen: [kitchen]   (befintligt / normaliserat / NYTT kök)

🥕 Ingredienser:
   - [kanoniskt namn] — [mängd] [enhet]   (befintlig)
   - [nytt namn] — [mängd] [enhet]        (NY: kategori=X, default_unit=Y)

👩‍🍳 Instruktioner:
   1. …
   2. …

📒 Notes:
   💡 Proffstips: …
   🔬 Vetenskap: …
   🎨 Alternativ: …

═══════════════════════════════════
Säg "push" för att spara,
eller ge feedback för att justera.
```

Visa **inte** recept-ID i previewen — servern tilldelar det vid spar.

### Steg 3 — Push

Bara när Nils har sagt **"push"**. Sourca `.claude/.env` och välj väg enligt "Spara-väg" ovan.

#### 3a — HTTP-API (normalfallet)

`POST $RECIPE_API_URL/api/recipe` med `Authorization: Bearer $RECIPE_API_TOKEN`. Body = receptet (samma fält som pending-schemat nedan, utan `operation`/`schema_version`/`created_*`). Befintliga ingredienser behöver bara `name`; nya kräver `grocery_category` + `default_unit`.

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $RECIPE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @- "$RECIPE_API_URL/api/recipe" <<'JSON'
{
  "title": "Snabbtacos med halloumi",
  "description": "… 4 portioner.",
  "instructions": "1. …\n2. …",
  "notes": "💡 Proffstips:\n- …\n🎨 Alternativ:\n- …",
  "tags": "tacos,vegetariskt,snabbt",
  "type": "huvudrätt",
  "kitchen": "🇲🇽 Mexikanskt",
  "ingredients": [
    {"name": "halloumi", "amount": "250", "unit": "g", "note": "",
     "grocery_category": "Mejeri", "default_unit": "g", "kitchen_staple": 0}
  ]
}
JSON
```

Svar `201` → `{"ok": true, "recipe_id": N, "version_number": 1, "changed_at": "..."}`. Bekräfta:

```
✅ Sparat i receptdatabasen (Pi)! [titel] (id: [recipe_id], version: 1)
   - [X] ingredienser kopplade ([Y] nya skapade)
```

Felhantering:
- `400` med `missing_fields` (`"error": "Ingredient not in catalog"`) → en ny ingrediens saknar `grocery_category`/`default_unit` (se `ingredient_name`). Fyll i och POSTa igen. Inget halvsparat blir kvar.
- `400` `title ... is required` → titel saknas.
- `401` → tokenen stämmer inte med Pi:ns. Be Nils om rätt token. **Skriv aldrig ut den.**
- `503` → `RECIPE_API_TOKEN` är inte satt på servern.
- Timeout / connection refused → Pi:n eller Tailscale nere (`tailscale status`). Erbjud pending-commit (3b).

#### 3b — Pending-commit (reserv)

1. Bygg commit-objekt (schema nedan) och skriv till `.claude/pending-commits/<ISO-timestamp>_<slug>.json`.
2. Bekräfta:

```
📦 Pending commit skapad: [filnamn]
   Appliceras via API:t när det går att nå — säg "apply pending"
   i Claude Code (eller kör scripts/skill_remote_commit.py).
```

## "apply pending"

När Nils säger **"apply pending"** eller **"push pending"**:

1. `ls .claude/pending-commits/` — om tomt, rapportera det.
2. Visa batch-preview: en rad per fil med filnamn och titel.
3. Vid bekräftelse: `python3 scripts/skill_remote_commit.py .claude/pending-commits/*.json`. Skriptet POSTar varje fil till `$RECIPE_API_URL/api/recipe` och flyttar filen till `.claude/applied-commits/` vid success. Vid fel ligger filen kvar.
4. Rapportera:

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
  "description": "… 4 portioner.",
  "instructions": "1. …\n2. …",
  "notes": "💡 Proffstips:\n- …\n🎨 Alternativ:\n- …",
  "tags": "tacos,vegetariskt,snabbt",
  "type": "huvudrätt",
  "kitchen": "🇲🇽 Mexikanskt",
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

Filnamn: `.claude/pending-commits/<YYYY-MM-DDTHH-MM-SSZ>_<slug>.json`. `slug` = gemener, bindestreck, ASCII-safe. Bara `operation: "create"` — edits går via `edit-recipe`.

## Viktiga regler

- **Skriv aldrig direkt till SQLite.** Enda skrivvägen är API:t (3a); pending-commit (3b) appliceras också via API:t.
- **ID**: tilldelas av servern. Hitta aldrig på eller hårdkoda ID:n.
- **Ingrediensmatchning**: mot katalogen från API:t, `name` + `aliases`, case-insensitive, kanoniskt namn.
- **Nya ingredienser**: `grocery_category` (från listan) + `default_unit` + `kitchen_staple` (1 för skafferivaror som salt/peppar/olja, annars 0).
- **Granularitet**: bara det som handlas separat. `äggula` ≠ ny rad.
- **Instruktioner**: numrerade steg med temp/tid, separerade med newlines.
- **notes**: proffstips + (vetenskap) + alternativ, aldrig tomt.
- **Visa alltid preview innan push** — spara först på "push".
- **Versionshistorik**: varje push loggar `recipe_version` v1 (servern gör det).
- **Edits → annan skill**: vill Nils ändra ett befintligt recept, säg "Det här är `edit-recipe`-territorium" och byt skill.
