---
name: edit-recipe
description: "Reflektera över ett redan publicerat recept efter att du lagat det, diskutera justeringar, och skapa en ny version i databasen. Triggas av /edit-recipe, eller fraser som 'jag lagade X igår', 'efterkok', 'reflektion kring [recept]', 'ändra/uppdatera/justera [recept]'. Skriver direkt till VPS-databasen via HTTP-API — fungerar lika bra från Cowork som från Claude Code."
---

# Edit-recipe Skill — Post-cook reflektion → ny version

## Profil
Läs `.claude/cowork-instructions.md` om den finns. Den definierar ton och samarbetsstil. Följ den.

## Syfte

Hjälp användaren att förbättra ett **redan publicerat** recept utifrån en konkret matlagningserfarenhet. Flödet är:

1. Användaren skriver en kort reflektion (t.ex. "Pad Thai blev för söt och nudlarna klumpade ihop sig").
2. Skillen hämtar nuvarande version från VPS-databasen.
3. Skillen föreslår 3–5 konkreta justeringar baserat på reflektionen.
4. Iterera tills användaren är nöjd.
5. Visa commit-preview med diff.
6. På **"push"** — skriv ny version till databasen via API.

Detta är skillen för **edits**. Nya recept hanteras av `recipe`-skillen (separat pending-commit-flöde).

## Språk

Allt på **svenska** — recepttitlar, fältinnehåll, change_note. Skillens UI-meddelanden mot användaren också på svenska.

## Konfiguration — `.claude/.env`

Skillen använder ett HTTP-API som ligger framför Flask-appen. Den behöver två env-variabler från `.claude/.env` (gitignored):

```
RECIPE_API_URL=https://din-domän.example
RECIPE_API_TOKEN=<lång slumpsträng, samma som på VPS>
```

Om filen eller variablerna saknas: rapportera tydligt och be användaren skapa `.claude/.env` (det finns en `.claude/.env.example` att kopiera). Kör inte vidare utan token.

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
```

Verifiera att variablerna är satta innan första API-anropet:

```bash
[ -n "$RECIPE_API_URL" ] && [ -n "$RECIPE_API_TOKEN" ] || echo "MISSING_CONFIG"
```

## Database-API (mellanlagret du anropar)

| Endpoint | Metod | Vad den gör |
|---|---|---|
| `/api/recipe/search?q=<text>` | GET | Sök recept på titel (substring, case-insensitive). Returnerar `{results: [{id, title, type, kitchen}]}`. |
| `/api/recipe/<id>` | GET | Full receptdata + `current_version_number` + ingredienser. |
| `/api/recipe/<id>/commit-edit` | POST | Skriv ny version. Body se nedan. |

Alla anrop kräver `Authorization: Bearer $RECIPE_API_TOKEN`.

### POST body-schema

```json
{
  "change_note": "Kort summering av reflektionen, t.ex. 'För söt — minskat palmsocker, justerade nudelinstruktioner'",
  "expected_version_number": 7,
  "title": "...",
  "description": "...",
  "instructions": "1. ...\n2. ...",
  "notes": "...",
  "tags": "...",
  "type": "...",
  "kitchen": "...",
  "ingredients": [
    {
      "name": "ris-nudlar",
      "amount": "180",
      "unit": "g",
      "note": "",
      "grocery_category": "Kolhydrater",
      "default_unit": "g",
      "kitchen_staple": 0
    }
  ]
}
```

- `change_note` är **obligatorisk** (står i version-historiken).
- `expected_version_number` = `current_version_number` du fick från GET. API:et returnerar 409 om någon annan editerade i mellantiden (t.ex. via webb-UI).
- Övriga fält är **valfria** — utelämnar du ett fält behåller API:et nuvarande värde. För `ingredients`: utelämna helt om du inte ändrar några; skickar du den ersätter den hela ingredienslistan.
- **Ingredient-namn måste matcha katalogen.** GET-svaret innehåller varje ingrediens med `name`, `grocery_category`, `default_unit` och `aliases`. Använd `name` exakt som det står — inte din egen variant. Om du måste lägga till en ny ingrediens skickar du `grocery_category` (från fasta listan) **och** `default_unit`, annars 400. För existerande ingredienser räcker `name` (eller ett alias).

### Svar

- `200` → `{"ok": true, "recipe_id": N, "new_version_number": N, "changed_at": "...", "change_note": "..."}`
- `400` → invalid input. Två varianter:
  - Generellt valideringsfel — visa `error`-fältet.
  - `error: "Ingredient not in catalog"` med `ingredient_name` + `missing_fields`. Be användaren bekräfta: ska ingrediensen läggas till med en viss kategori + default_unit, eller är det en felstavning av något som redan finns? Försök först alias-matcha mot katalogen.
- `401` / `503` → token/konfig-problem (be användaren kolla `.claude/.env` och `RECIPE_API_TOKEN` på VPS)
- `404` → recept finns inte
- `409` → version-konflikt. Hämta recept igen, fråga användaren om de vill bygga om sin edit.
- `500` → DB-fel, visa felet, fråga om de vill försöka igen.

## Arbetsflöde

### Steg 1 — Lokalisera receptet

Användaren skriver typiskt något som *"Jag lagade Pad Thai igår — den var för söt"*. Identifiera receptnamnet och sök:

```bash
curl -sS -H "Authorization: Bearer $RECIPE_API_TOKEN" \
  "$RECIPE_API_URL/api/recipe/search?q=pad%20thai"
```

- 0 träffar → fråga användaren om annan stavning eller om de vill skapa nytt recept istället.
- 1 träff → kör vidare med det id:et.
- Flera träffar → lista titlarna med id, låt användaren välja.

Hämta sedan full receptdata:

```bash
curl -sS -H "Authorization: Bearer $RECIPE_API_TOKEN" \
  "$RECIPE_API_URL/api/recipe/42"
```

Spara `current_version_number` — den ska skickas tillbaka som `expected_version_number`.

### Steg 2 — Förstå reflektionen och föreslå justeringar

Visa i chatten en kompakt sammanfattning av nuvarande recept (titel, version, kärningredienser, kärninstruktioner). Föreslå sedan 3–5 **konkreta** justeringar utifrån reflektionen:

```
🍳 Pad Thai (id: 42, version 7)

Din reflektion: "för söt och nudlarna klumpade ihop sig"

Förslag på justeringar:

1. Sänk palmsocker från 3 msk → 2 msk (jämnare sötma).
2. Förkorta nudel-blötläggning från 8 → 5 min, skölj efter med kallt vatten
   så de inte kletar.
3. Lägg till ett sista vänd-i-pannan-steg innan servering så
   såsen klär nudlarna istället för att klumpa.
4. Lite mer limesaft i såsen (1 → 1.5 msk) för att balansera sötma.

Låter detta rimligt? Vill du justera något, eller säg "push" så
implementerar jag och skapar version 8.
```

Var praktisk och konkret. Föreslå inte breda omskrivningar — håll dig till det reflektionen pekar på.

### Steg 3 — Iterera

Användaren kan:
- **Acceptera allt** → gå till commit preview.
- **Be dig justera** ("nej, sänk till 1.5 msk istället") → uppdatera ditt förslag, visa igen.
- **Lägga till idéer** ("kan vi också byta ut räkorna mot kyckling?") → ta in det i förslaget.

### Steg 4 — Commit preview

Innan push, visa **alltid** preview i samma format som `recipe`-skillen använder:

```
📝 COMMIT PREVIEW — REDIGERING
═══════════════════════════════════

📖 Recept: Pad Thai (id: 42)
   Nuvarande version: 7  →  Ny version: 8

✏️  Ändringar:

   instructions:
   ❌ Före: "1. Blötlägg nudlarna i 8 min..."
   ✅ Efter: "1. Blötlägg nudlarna i 5 min, skölj med kallt vatten..."

   🔄 Ändrade ingredienser:
      - palmsocker: 3 msk → 2 msk
      - limesaft: 1 msk → 1.5 msk

   (Övriga ingredienser oförändrade.)

📝 change_note: "För söt och klumpiga nudlar — minskat socker, justerade nudelinstruktioner, mer lime"

═══════════════════════════════════
Säg "push" för att spara,
eller ge feedback för att justera.
```

Generera en kortfattad `change_note` (en mening, max ~120 tecken) som speglar reflektionen. Den blir titel i version-historiken.

### Steg 5 — Push

På **"push"** (eller "spara", "skicka"), POSTa till API:et. **Bygg payloaden i Python eller med `jq`**, inte med naken bash-string-konkatenering:

```bash
python3 - <<'PY' > /tmp/edit_payload.json
import json
payload = {
    "change_note": "För söt och klumpiga nudlar — minskat socker, justerade nudelinstruktioner",
    "expected_version_number": 7,
    "instructions": "1. Blötlägg nudlarna...\n2. ...",
    "ingredients": [
        # Existerande ingrediens — räcker med name (kanoniskt) + amount/unit/note.
        {"name": "palmsocker", "amount": "2", "unit": "msk"},
        # Ny ingrediens — kräver grocery_category + default_unit:
        # {"name": "tamarindpasta", "amount": "1", "unit": "msk",
        #  "grocery_category": "Smaksättare", "default_unit": "msk", "kitchen_staple": 0},
        # ... resten av ingredienserna
    ],
}
print(json.dumps(payload, ensure_ascii=False))
PY

curl -sS -X POST \
  -H "Authorization: Bearer $RECIPE_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d @/tmp/edit_payload.json \
  "$RECIPE_API_URL/api/recipe/42/commit-edit"
```

Bekräftelse efter success:

```
✅ Sparat! Pad Thai är nu version 8.
   📝 "För söt och klumpiga nudlar — minskat socker, justerade nudelinstruktioner, mer lime"

   Se diff: $RECIPE_API_URL/recipe/42/diff?from=7&to=8
   Historik: $RECIPE_API_URL/recipe/42/history
```

(Om `RECIPE_API_URL` slutar på `/api/...` så strippa det — diff/history-länkarna ligger på rot-domänen.)

### Felfall

| Status | Hantering |
|---|---|
| 401 / 503 | "Token saknas eller är fel — kolla `.claude/.env` (Cowork) eller `RECIPE_API_TOKEN` på VPS." |
| 404 | "Receptet med id N finns inte i databasen längre." |
| 409 | "Någon annan editerade receptet (förmodligen via webb-UI). Hämtar senaste versionen — vill du bygga om din edit på den?" Hämta GET igen, visa skillnaden, fråga. |
| 500 / nätverksfel | Visa felet rakt, fråga om retry. |

## Viktiga regler

- **Visa alltid preview innan push.** Ingen tyst skrivning till databasen.
- **change_note är obligatorisk.** Den ska beskriva *varför* ändringen gjordes (reflektionen), inte *vad* (det syns redan i diffen).
- **expected_version_number** ska alltid skickas — det är skyddsnätet mot konflikter.
- **Skicka bara fält som faktiskt ändras** i payloaden (utöver `change_note` och `expected_version_number`). Det gör diffar i historiken renare.
- **Kanoniska ingrediensnamn**: använd `name` exakt som det stod i GET-svaret. Kolla `aliases`-arrayen innan du föreslår en "ny" ingrediens — den kan redan finnas som alias. Tillåtna kategorier: `Frukt och grönt`, `Färska örter`, `Mejeri`, `Kött`, `Fågel`, `Fläsk`, `Fisk`, `Kolhydrater`, `Baljväxter`, `Konserver`, `Smaksättare`, `Färdiga tillbehör`, `Bageri`, `Frys`, `Alkohol`, `Övrigt`. Nya ingredienser kräver också `default_unit`.
- **Granularitet**: katalogen rymmer bara saker som inhandlas separat. Skriv `ägg` (inte `äggula`), `vitlök` (inte `vitlöksklyfta`). Nyans hör hemma i `recipe_ingredient.note` ("endast gula", "rivna").
- **Image-fältet rörs inte** av det här flödet — bilduppladdning sker i webb-UI.
- **Inga ID:n hårdkodas.** Slå alltid upp recept med `/api/recipe/search` först.
- **Token loggas aldrig.** Skriv inte ut `$RECIPE_API_TOKEN` i meddelanden eller filer. Kasta inte `curl -v` mot användaren utan att redacta headern.
- **Om API:et inte är konfigurerat:** stoppa flödet tidigt med tydlig instruktion. Försök inte falla tillbaka på pending-commits — det är `recipe`-skillens ansvar för nya recept.

## Diagnostik (när användaren felsöker)

```bash
# Sanity-check att API:et lever och token är korrekt:
curl -sS -o /dev/null -w "%{http_code}\n" \
  -H "Authorization: Bearer $RECIPE_API_TOKEN" \
  "$RECIPE_API_URL/api/recipe/search?q=test"
# 200 = OK. 401 = fel token. 503 = token inte satt på server. 404 = fel URL/path.
```
