# Workflow Overhaul Plan

Detaljerad plan för omställningen av receptdatabasens workflow. Täcker rollfördelning mellan Cowork och Claude Code, synkronisering, versionshistorik, inköpslistor och Notion Kanban.

## Bakgrund och mål

Tidigare arkitektur använde Turso + Render + Supabase. Projektet har migrerats till ren SQLite + en VPS med Docker + GitHub Actions-deploy. Denna plan rensar upp efter migrationen och bygger det workflow användaren faktiskt vill ha:

- Planering av experimentella recept i en Notion Kanban.
- Skapande/redigering av recept via Claude i chatten (recipe-skill).
- Redigering via Flask-appens webb-UI (från vilken enhet som helst).
- Inköpslistor genererade i webb-UI:t från valda recept.
- Versionshistorik med diff-vy.

## Rollfördelning Cowork vs Claude Code

Sandboxen i Cowork har inte nätverksaccess till VPS. Därför delas arbetet:

**Cowork (desktop-app, sandboxed):**
- Brainstorma recept med användaren.
- Skriva pending-commits till `.claude/pending-commits/` som JSON.
- Hantera Notion Kanban via Notion MCP.
- Filredigering som inte kräver VPS-åtkomst (Flask-features, templates, docs).

**Claude Code (terminal på Macbook):**
- Läsa pending-commits och applicera dem mot VPS:ens `recipe.db` via SSH (`ssh minvps`).
- Redigera befintliga recept direkt mot VPS.
- Köra migrationer mot VPS-databasen.
- Allt som kräver SSH-åtkomst eller att köra saker på riktig data.

Båda kör samma `recipe`-skill; den detekterar vilken miljö den är i och beter sig därefter.

## Infrastruktur och faser

### Fas 1 — Cleanup (klar, gjord i Cowork)

- Tagit bort Turso-, Render- och Supabase-spår från `app.py`, `requirements.txt`, `requirements-prod.txt`, `Dockerfile`, `render.yaml`.
- Förenklat `Dockerfile` (ingen Rust/clang/cmake — de fanns bara för `libsql`).
- Uppdaterat `CLAUDE.md` med ny arkitektur, working modes-sektion och uppdaterad scope.
- Bytt namn på `scripts/turso_to_sqlite.py` till `scripts/csv_to_sqlite.py`.
- Raderat `dev.db` (tom), `render.yaml`, `requirements-prod.txt` (användaren måste köra `rm` själv — sandbox kan inte).
- Lagt till `.claude/`-subfoldrar i `.gitignore`.

### Fas 2 — Versionshistorik i databasen (Claude Code)

Ny tabell `recipe_version`:

```sql
CREATE TABLE recipe_version (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recipe_id INTEGER NOT NULL,
    version_number INTEGER NOT NULL,
    title TEXT,
    description TEXT,
    instructions TEXT,
    notes TEXT,
    image_url TEXT,
    tags TEXT,
    section TEXT,
    menu TEXT,
    ingredients_json TEXT,      -- serialized list of {ingredient_id, name, amount, unit, note}
    changed_at TEXT NOT NULL,   -- ISO timestamp
    changed_by TEXT,            -- 'chat' | 'web' | 'migration'
    change_note TEXT,
    FOREIGN KEY (recipe_id) REFERENCES recipe(id)
);
CREATE INDEX idx_recipe_version_recipe ON recipe_version(recipe_id, version_number);
```

Steg:

1. Skapa `scripts/migrations/001_recipe_version.py` som:
   - Skapar tabellen om den inte finns.
   - Backfill:ar en version 1 per befintligt recept (10 rader i nuläget), med `changed_by = 'migration'`.
   - Idempotent — kan köras flera gånger utan att göra dubbletter.
2. Kör migrationen lokalt mot `recipe.db` (om filen finns) och mot VPS via `ssh minvps "cd /opt/recipe-db && python3 scripts/migrations/001_recipe_version.py"` eller motsvarande.
3. Hook:a `edit_recipe`-routen i `app.py` att skriva en version-rad *före* UPDATE (läs nuvarande state, spara till `recipe_version` med `changed_by='web'`).

### Fas 3 — Skill talar till VPS (Claude Code)

Bygg `scripts/skill_remote_commit.py` som helper:

- Tar ett commit-objekt som JSON via stdin.
- Beroende på `operation`-fält: `create` → INSERT, `update` → UPDATE.
- Öppnar SSH-kanal till `minvps`, kör via `python3 -` så SQL-transaktionen sker på VPS:ens SQLite-fil direkt.
- Inom samma transaktion: logga en `recipe_version`-rad med `changed_by='chat'`.
- Returnerar strukturerat svar: `{status: ok|error, recipe_id: int, version_number: int}`.

Uppdatera `recipe/SKILL.md` så att:

- I Claude Code-läge anropas helpern direkt vid push.
- "apply pending"-kommando läser alla filer från `.claude/pending-commits/`, visar batch-preview, bekräftar, kör helper per commit, flyttar tillämpade till `.claude/applied-commits/`.

Efter Fas 3: end-to-end test — skapa recept i Cowork, växla till Claude Code, säg "apply pending", verifiera på hemsidan.

### Fas 4 — Diff-UI i Flask

- `GET /recipe/<id>/history` — tabell av versioner: datum, `changed_by`, `change_note`, länk till diff.
- `GET /recipe/<id>/diff?from=<v>&to=<v>` — side-by-side diff via `difflib.HtmlDiff` för textfält (instructions, description, notes), strukturerad diff för ingredienslistan (added/removed/modified).
- Länk från `recipe_detail.html` → "Versionshistorik".

### Fas 5 — Inköpslistor i Flask

- `GET /shopping-list` — recept-picker (checkbox-galleri som återanvänder gallery-layouten).
- `POST /shopping-list/generate` — konsoliderad lista grupperad på `grocery_category`:
  - Enhets-aggregering: samma ingrediens + samma enhet → summering av `amount` (tolka som float där möjligt).
  - Separat rad om enheter skiljer sig (`mjölk: 2 dl + 100 ml`).
  - Toggle "Dölj skafferivaror" baserat på `kitchen_staple`.
  - Print-friendly CSS (`@media print`).

Scope-uppdateringen i `CLAUDE.md` är redan gjord (inköpslistor = in scope för webb-UI, out of scope för skillen).

### Fas 6 — Notion Kanban

Görs i Cowork efter att Notion MCP är ansluten.

Databas i Notion: `Recept-pipeline`.

Properties:
- `Titel` (title)
- `Beskrivning` (text)
- `Ingredienser (utkast)` (text eller rich text)
- `Instruktioner (utkast)` (text)
- `Anteckningar från matlagning` (text)
- `Recipe ID` (number, nullable — fylls i när receptet är pushat)
- `Senast lagad` (date)
- `Status` (select med alternativen nedan)

Kanban-vy grupperad på `Status`:
- `Idé`
- `Tillagad`
- `Publicerad`

Arbetsflöde: användaren flyttar kort manuellt. Auto-synk från skill → Notion kan komma i en senare fas om det behövs.

## Föreslagen ordning och tidsuppskattning

1. **Fas 1** — klar.
2. **Fas 2** (migration) — 30 min, kräver Claude Code.
3. **Fas 3** (skill ↔ VPS) — 1–2 h, Claude Code.
4. **End-to-end test** — 15 min.
5. **Fas 5** (inköpslistor) — 1–2 h, kan göras i antingen miljö men Claude Code är naturligt.
6. **Fas 4** (diff-UI) — 1–2 h.
7. **Fas 6** (Notion) — 30 min, Cowork.

## Konventioner

**Pending-commit JSON-schema** (skapas av Cowork, konsumeras av Claude Code):

```json
{
  "schema_version": "1",
  "operation": "create",
  "title": "Snabbtacos med halloumi",
  "description": "...",
  "instructions": "1. Steka halloumi...\n2. ...",
  "notes": null,
  "image_url": null,
  "tags": "vegetariskt,tacos",
  "section": "Tacos",
  "menu": "🌮 Mexikanskt",
  "ingredients": [
    {
      "name": "halloumi",
      "amount": "250",
      "unit": "g",
      "note": "",
      "kitchen_staple": 0,
      "grocery_category": "Mejeri"
    }
  ],
  "created_at": "2026-04-19T22:30:00Z",
  "created_by": "cowork"
}
```

För `update` inkluderas `recipe_id` och `change_note` istället för ny ID-tilldelning.

**Filnamnsmönster**: `.claude/pending-commits/<ISO-timestamp>_<slug>.json`
