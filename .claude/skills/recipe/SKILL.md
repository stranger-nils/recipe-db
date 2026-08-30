---
name: recipe
description: "Brainstorma receptidéer, föreslå kompletta recept på svenska och spara nya recept till SQLite-databasen. Triggas när användaren vill ha receptförslag, matinspiration, middagstips, eller spara ett nytt recept. Nyckelord: recept, middag, mat, laga, ingredienser, spara recept, push, brainstorm. För att redigera/uppdatera/justera ett befintligt recept — använd skillen edit-recipe istället."
---

<!-- SKILL_VERSION: 2026-08-21 -->

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

## Spara-vägar — HTTP-API först

Nya recept sparas via **HTTP-API:t** (`POST /api/recipe`) — samma mellanlager som `edit-recipe` använder. Det fungerar **i båda miljöerna** (Cowork och Claude Code), kräver ingen SSH, och är **förstahandsvalet**. API:t skapar receptet, kopplar ingredienser och loggar `recipe_version` v1 i en transaktion — och returnerar ett tydligt fel om en ny ingrediens saknar `grocery_category`/`default_unit`, så du kan rätta direkt utan manuell granskning.

Två reservvägar finns kvar för när API:t inte är konfigurerat/nåbart:
- **Pending-commit** (Cowork utan API): skriv commit till fil, Claude Code applicerar senare.
- **Direkt SSH** (Claude Code): kör transaktion mot VPS-DB:n.

**Välj väg vid push:**

1. Sourca `.claude/.env` och kontrollera `RECIPE_API_URL` + `RECIPE_API_TOKEN` (se Konfiguration nedan).
2. Är båda satta → **använd HTTP-API:t** (Steg 3a). Detta är normalfallet, oavsett miljö.
3. Saknas konfig → fall tillbaka: pending-commit i Cowork (Steg 3b), eller direkt SSH om `ssh minvps` svarar (Steg 3c, Claude Code).

Kommunicera tydligt vid push vilken väg som användes ("sparad direkt till VPS via API" vs "sparad som pending commit — växla till Claude Code för att applicera").

## Konfiguration — `.claude/.env`

HTTP-API:t kräver två env-variabler från `.claude/.env` (gitignored, samma fil som `edit-recipe` använder):

```
RECIPE_API_URL=https://din-domän.example
RECIPE_API_TOKEN=<lång slumpsträng, samma som på VPS>
```

Saknas filen/variablerna: använd en reservväg (pending-commit eller SSH). Det finns en `.claude/.env.example` att kopiera.

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

## ⚠️ Vanliga fallgropar — läs INNAN du sparar

Gäller **både** API-body (`POST /api/recipe`) och pending-commit JSON:

1. **Fältnamnen är `type` och `kitchen`** — INTE `section`/`menu`. Det gamla schemat döptes om i migration 005. Använder du `section`/`menu` kommer recepten sparas med NULL i kategorisering.
2. **Varje *ny* ingrediens MÅSTE ha `default_unit`** (inte bara `unit`) **och** `grocery_category`. Båda är NOT NULL/CHECK i DB:n — saknas något rejectas en ny ingrediens (API svarar 400 med `missing_fields`).
3. **`kitchen`/`type` sätts ALDRIG ur minnet eller från exempel — de MÅSTE bygga på en live-query mot prod.** Kör query-steget i "Kategoriseringskonventioner" (`GET /api/recipe/search?q=`) innan varje preview och kopiera värdet därifrån.
4. **`kitchen` skrivs ALLTID som emoji + mellanslag + text** (`"🇮🇹 Italienskt"`, `"🍜 Asiatiskt"`) — aldrig bara `"Italienskt"`. **`type` är en kort maträttstyp med inledande versal** utan emoji (`"Tacos"`, `"Wok"`). Finmaskigare beskrivning (t.ex. `salsa`, `snabbt`, `vegetariskt`) hör hemma i `tags`.

Se de fullständiga schemana längre ner — kopiera från dem, inte från minnet.

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

I Cowork-läge finns en lokal `recipe.db` i projektroten som en **read-only snapshot** av VPS-databasen.

> ⚠️ **Snapshoten är ofta månadsgammal och får ALDRIG vara auktoritativ när API:t är konfigurerat.**
> Den uppdateras bara manuellt och ligger i praktiken långt efter prod. Observerat fall: snapshoten
> innehöll 97 ingredienser och 3 `kitchen`-värden medan prod hade 203 respektive 18 — vilket ledde till
> att redan existerande ingredienser (`jätteräkor`, `flingsalt`) föreslogs som NYA i previewen.
> Använd snapshoten **endast** som fallback när `RECIPE_API_URL`/`RECIPE_API_TOKEN` saknas, och flagga
> då i previewen att matchningen är best-effort mot inaktuella data.

När den ändå används är det för:
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

1. **Bygg ingredienskatalogen från PROD** — obligatoriskt när API:t är konfigurerat, precis som för `kitchen`/`type`. Det finns ingen `/api/ingredient`-endpoint, så katalogen härleds genom att hämta alla recept och samla deras ingrediensnamn (kodblocket nedan). Slå upp mot både `name` (NOCASE) **och** `aliases`. Endast om API-konfig saknas: fall tillbaka på lokal snapshot och flagga det i previewen.
2. **Matchar något** → använd det kanoniska namnet exakt som det står i DB. Inte din egen variant.
3. **Granularitet**: katalogen ska bara innehålla saker som **handlas separat i butik**. Exempel:
   - `ägg` finns. `äggula`/`äggvita` finns **inte** — det är samma inköp. Skriv `ägg` som ingrediens och lägg "endast gulor" i `recipe_ingredient.note`.
   - `gullök` och `silverlök` finns separat (olika inköp).
   - `vitlök` finns (default_unit `klyfta`). Skriv aldrig `vitlöksklyfta` som egen rad — det är ett alias.
4. **Ny ingrediens behövs** → du måste alltid ange `grocery_category` (från listan ovan) **och** `default_unit` i pending-commit/preview. Annars rejectar DB:n (CHECK + NOT NULL).

**Lookup-mönster A — mot PROD via API (förstahandsval):**
```python
import json, os, urllib.request
base, tok = os.environ['RECIPE_API_URL'], os.environ['RECIPE_API_TOKEN']

def _get(path):
    req = urllib.request.Request(base + path, headers={'Authorization': 'Bearer ' + tok})
    return json.load(urllib.request.urlopen(req))

def prod_ingredient_catalog():
    """{lowercase namn: set(enheter)} härlett ur alla recept i prod."""
    res = _get('/api/recipe/search?q=')
    rows = res['results'] if isinstance(res, dict) else res
    cat = {}
    for r in rows:
        d = _get('/api/recipe/%d' % r['id'])
        for ing in (d.get('ingredients') or d.get('recipe', {}).get('ingredients') or []):
            if ing.get('name'):
                cat.setdefault(ing['name'].lower(), set()).add(ing.get('unit') or '')
    return cat
```

Markera en ingrediens som `(NY)` i previewen **först** när den saknas i den här prod-katalogen — aldrig utifrån snapshoten.

**Lookup-mönster B — mot lokal snapshot (endast utan API-konfig):**
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

### Kategoriseringskonventioner (kitchen, type, tags)

**Källan för namngivning är PROD-databasen — aldrig exempel i den här filen och aldrig ditt minne.** Innan du föreslår `kitchen`/`type` i en commit-preview MÅSTE du hämta de befintliga värdena live via API:t (obligatoriskt steg, ingen genväg):

```bash
set -a; source <path till .claude/.env>; set +a
curl -sS -H "Authorization: Bearer $RECIPE_API_TOKEN" \
  "$RECIPE_API_URL/api/recipe/search?q=" \
| python3 -c "
import json, sys
rows = json.load(sys.stdin)['results']
print('KITCHEN:', sorted({r['kitchen'] for r in rows if r['kitchen']}))
print('TYPE:',    sorted({r['type']    for r in rows if r['type']}))
"
```

(`q=` tomt → alla recept med `kitchen`/`type` returneras.) Endast om API:t inte är konfigurerat: fall tillbaka på lokal snapshot (`SELECT DISTINCT kitchen FROM recipe` osv.) — men flagga då i previewen att listan kan vara inaktuell.

**Välj `kitchen` så här, i ordning:**

1. **Exakt emoji-variant finns i query-resultatet** (t.ex. `🇮🇹 Italienskt`) → använd den strängen tecken för tecken. Kopiera från query-utdatan, skriv den inte ur minnet.
2. **Bara en variant utan emoji finns** (legacy-data, t.ex. `Italienskt`) → använd INTE den rakt av. Bilda emoji-varianten av samma text (`🇮🇹 Italienskt`) och markera i previewen att det är en normaliserad variant av ett befintligt värde.
3. **Köket finns inte alls** → skapa nytt enligt mönstret **emoji + mellanslag + text med inledande versal**: flaggemoji för nationella kök (`🇮🇹 Italienskt`), annars en passande emoji (`🍜 Asiatiskt`, `🍲 Grunder`). Markera i previewen med `(NYTT kök)`.

`kitchen` utan emoji är ALLTID fel att skriva — även om prod råkar innehålla sådana legacy-värden.

**`type`**: samma princip — kör samma query och återanvänd ett befintligt värde exakt om det passar (t.ex. `Tacos`, `Nudlar`, `Wok`). Ingen emoji. Inget passar → nytt kort värde med inledande versal, markerat `(NYTT)` i previewen.

**`tags`**: kommaseparerade, gemener: t.ex. `italiensk,pasta` eller `stark, nötkött`. Ingen emoji.

## Arbetsflöde — Nytt recept

### Steg 1 — Brainstorming
Ge **kompletta** receptförslag direkt (titel, beskrivning, ingredienser med mängd/enhet, numrerade instruktioner). Anpassa efter användarens önskemål. Var kreativ men praktisk — rätter man faktiskt vill laga hemma.

### Steg 2 — Commit preview

När användaren gillar ett recept och vill spara:

1. **Bygg ingredienskatalogen från prod** via API:t (`prod_ingredient_catalog()`) och matcha mot den. Snapshot/VPS-läsning används bara om API-konfig saknas.
2. **Hämta befintliga `kitchen`/`type`-värden från prod** med query-steget i "Kategoriseringskonventioner" (`GET $RECIPE_API_URL/api/recipe/search?q=`). Detta är obligatoriskt — hoppa aldrig över det.
3. **Föreslå kategorisering** utifrån query-resultatet: `tags` (gemener, kommaseparerade), `type` (befintligt värde eller nytt med versal, markera `(NYTT)`), `kitchen` (befintlig emoji-variant exakt som i prod, eller normaliserad/ny enligt reglerna — ALLTID emoji + text).
4. **Visa preview:**

```
📝 COMMIT PREVIEW — NYTT RECEPT
═══════════════════════════════════

📖 Recept: [titel]
   tags: [tags]
   type: [type]         (befintligt i prod / NYTT)
   kitchen: [kitchen]   (befintligt i prod / normaliserat / NYTT kök)

🥕 Ingredienser:
   - [kanoniskt namn] — [mängd] [enhet]   (existerande)
   - [nytt namn] — [mängd] [enhet]        (NY: kategori=X, default_unit=Y)
   - ...

═══════════════════════════════════
Säg "push" för att spara,
eller ge feedback för att justera.
```

Visa **inte** numeriska recept-ID:n i previewen — de tilldelas först vid spar (API:t/VPS returnerar ID). Undantag: 3c (direkt SSH) där du kan visa preliminärt ID (MAX(id)+1 från VPS).

### Steg 3 — Push

Sourca `.claude/.env` och välj väg enligt "Spara-vägar" ovan: **3a om API är konfigurerat** (normalfallet), annars reservväg 3b/3c.

#### 3a — HTTP-API (förstahandsval, båda miljöerna)

`POST $RECIPE_API_URL/api/recipe` med `Authorization: Bearer $RECIPE_API_TOKEN`. Body = receptet (samma fält som schemat nedan, utan `operation`/`schema_version`). Befintliga ingredienser behöver bara `name` (kanoniskt namn eller alias); nya kräver `grocery_category` + `default_unit`.

```bash
curl -sS -X POST \
  -H "Authorization: Bearer $RECIPE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @- "$RECIPE_API_URL/api/recipe" <<'JSON'
{
  "title": "Snabbtacos med halloumi",
  "description": "...",
  "instructions": "1. ...\n2. ...",
  "notes": null,
  "tags": "vegetariskt,tacos",
  "type": "Tacos",
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
✅ Sparat via API! [titel] (id: [recipe_id], version: 1)
   - [X] ingredienser kopplade ([Y] nya skapade)
```

Felhantering:
- `400` `"error": "Ingredient not in catalog"` → en ny ingrediens saknar `grocery_category`/`default_unit` (se `missing_fields` + `ingredient_name`). Fyll i och posta om. Hela inserten rullas tillbaka — inget halvsparat recept blir kvar.
- `400` `title ... is required` → titel saknas/tom.
- `401` / `503` → token/konfig-problem (kolla `.claude/.env` och `RECIPE_API_TOKEN` på VPS). **Logga aldrig token.**

#### 3b — Pending-commit (reserv: Cowork utan API-konfig)

1. Bygg commit-objekt (schema nedan), skriv till `.claude/pending-commits/<ISO-timestamp>_<slug>.json`.
2. Bekräfta:

```
📦 Pending commit skapad: [filnamn]
   Öppna Claude Code i projektmappen och säg "apply pending"
   för att skriva till VPS-databasen.
```

#### 3c — Direkt SSH (reserv: Claude Code utan API-konfig)

Via SSH, kör en transaktion mot `/opt/recipe-db/data/recipe.db`:
- MAX(id) + 1 för nytt recept.
- För varje ingrediens: `LOWER(name)`-matcha → återanvänd ID eller skapa ny.
- INSERT i `recipe`, `recipe_ingredient`, samt `recipe_version` (`version_number = 1`, `changed_by = 'chat'`, `changed_at = <ISO-timestamp>`, `ingredients_json = <serialiserad lista>`).

```
✅ Sparat på VPS! [titel] (id: [id], version: 1)
   - [X] ingredienser kopplade ([Y] nya skapade)
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
  "type": "Tacos",
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

Filnamn: `.claude/pending-commits/<YYYY-MM-DDTHH-MM-SSZ>_<slug>.json`. `slug` = lowercase, bindestreck istället för mellanslag, ASCII-safe.

> **Notera:** `operation: "update"` används inte längre i pending-commit-flödet — edits hanteras av `edit-recipe`-skillen via HTTP-API. Den här skillen ska bara producera `create`-commits.

## Viktiga regler

- **ID-hantering**: Via API:t (3a) tilldelas och returneras ID:t av servern — hitta aldrig på det. Bara i SSH-vägen (3c) läser du MAX(id) själv. Aldrig hårdkodade ID:n.
- **Ingrediensmatchning**: mot **prod-katalogen** (API), NOCASE + alias-lookup. Använd alltid kanoniskt namn från DB:n, aldrig din egen stavning om det finns en träff. Lokal snapshot är fallback och flaggas i previewen.
- **Nya ingredienser**: kräver `grocery_category` (från listan) + `default_unit` + `kitchen_staple` (1 för skafferisaker som salt/peppar/olja, annars 0). Saknas något → DB:n rejectar med CHECK/NOT NULL.
- **Granularitet**: bara det som inhandlas separat. `äggula` ≠ ny rad. `gullök` vs `silverlök` = separata rader.
- **Instruktioner**: Numrerade steg, separerade med newlines.
- **notes**: NULL om inget speciellt.
- **Transaktioner**: API:t (3a) gör hela sparet atomiskt. I SSH-vägen (3c) kapsla in allt i `BEGIN; ... COMMIT;` (ROLLBACK vid fel).
- **Visa alltid preview innan push** — aldrig direkt till DB utan bekräftelse.
- **Versionshistorik**: Varje push (nytt eller edit) loggar en rad i `recipe_version`.
- **Lokal snapshot skrivs aldrig**: lokal `recipe.db` är strikt read-only (ingrediens-matching/preview). Skrivning går via API (3a), pending-commit (3b) eller SSH mot VPS (3c) — aldrig mot snapshoten.
- **Edits → annan skill**: Om användaren vill ändra ett befintligt recept, säg "Det här är `edit-recipe`-territorium — invokera den" istället för att gå vidare.
