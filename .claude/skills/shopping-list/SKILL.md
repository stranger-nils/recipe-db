---
name: shopping-list
description: "Skapa en konsoliderad inköpslista från ett antal recept i Notion (Recept-pipeline) och spara den som en ny sida i Notion-databasen Inköpslistor — kategoriserad per butiksavdelning. Triggas när användaren säger 'inköpslista', 'shoppinglista', 'handla', 'helgens matlagning', 'skapa lista' eller liknande, OCH räknar upp recept som ska ingå. Nyckelord: inköpslista, handlingslista, handla, shopping, helgens recept, vad ska jag handla."
---

# Shopping-list Skill — Inköpslistor från recept

## Profil
Läs `.claude/cowork-instructions.md` om den finns. Den definierar ton och samarbetsstil. Följ den i alla interaktioner.

## Syfte
När Nils räknar upp ett antal recept han vill laga, hämta dem från Notion-databasen **Recept-pipeline**, konsolidera ingredienserna, kategorisera per butiksavdelning, och spara som en ny sida i Notion-databasen **Inköpslistor**.

Tänk dig själv som hans handlingsmedhjälpare: målet är att han kan öppna noten i mobilen i butiken och bocka av effektivt utan att hoppa fram och tillbaka mellan avdelningar.

## Språk
Allt innehåll på **svenska**.

## Notion-integration

### Databaser

- **Källa — Recept-pipeline:** `data_source_id = bafc508d-701f-48ec-985b-877de7cc1a5c` (under sidan Recept-labb)
- **Mål — Inköpslistor:** `data_source_id = 6988ad6c-4c42-4a4d-83fa-2d91bda0c965` (under samma Recept-labb-sida)

### Inköpslistor-schema

| Property | Typ | Beskrivning |
|---|---|---|
| Titel | title | T.ex. "Inköpslista — Schnitzel + Fond + Poulet rôti" |
| Datum | date | Datum listan gäller (default: idag) |
| Status | select | "Att handla" (default), "Handlad", "Arkiverad" |
| Recept | text | Kommaseparerad lista över recepten som ingår |
| Anteckningar | text | Antaganden, val (t.ex. rotfruktskombo), portioner |

Sidans **body** innehåller den faktiska listan, organiserad i kategori-headers.

### Recept-pipeline — relevanta fält

- `Titel` — receptnamn (för matchning)
- `Beskrivning` — kontext (t.ex. portioner)
- `Ingredienser (utkast)` — ingredienslista (parsa rad-för-rad)

## Arbetsflöde

### Steg 1 — Identifiera recepten

Användaren räknar upp recept. Exempel: *"Helgens matlagning. Schnitzel, Fond, Poulet rôti."*

För varje namn:
1. Kör `notion-search` mot Recept-pipeline (`data_source_url = collection://bafc508d-701f-48ec-985b-877de7cc1a5c`).
2. Vid flera träffar: lista och låt Nils välja.
3. Vid ingen träff: rapportera och fråga om han vill söka bredare eller skippa.

### Steg 2 — Hämta ingredienser

För varje träff: `notion-fetch` på sidans ID. Plocka ut `Ingredienser (utkast)`-fältet.

Var beredd på olika format:
- Bullet-lista (`- ingrediens — mängd enhet`)
- Sektioner med headers (t.ex. "Marinad + ragù:", "Servering:")
- HTML `<br>`-taggar mitt i textfältet (Notion-quirk)

Parsa **alla** ingredienser även om de ligger i flera sektioner.

### Steg 3 — Konsolidera

Slå ihop dubbletter:
- *"1 citron"* (Schnitzel) + *"1 citron"* (Poulet) → *"2 citroner"*
- Olika enheter? Konvertera om enkelt (t.ex. dl ↔ ml), annars håll separat med kommentar.
- Olika namn för samma sak? Använd kunskap (t.ex. "gul lök" + "lök" → samma).

Notera per ingrediens vilka recept den kommer ifrån. Det blir kommentar i listan: *"~700 g morötter (2 fond + 4–5 poulet)"*.

### Steg 4 — Kategorisera per butiksavdelning

Använd dessa kategorier (i denna ordning, motsvarar typisk butiks-flow):

| Emoji | Kategori | Exempel |
|---|---|---|
| 🥩 | Kött & fågel | fläskkotlett, märgben, kyckling, korv |
| 🐟 | Fisk & skaldjur | lax, räkor, musslor |
| 🥕 | Frukt & grönt | citron, lök, morot, potatis, vitlök, gurka |
| 🌿 | Färska örter | persilja, dill, timjan, basilika |
| 🥚 | Mejeri & ägg | smör, ägg, parmesan, grädde, mjölk |
| 🥫 | Skafferi / torrt | mjöl, ströbröd, pasta, ris, olja, kryddor (icke-staple), tomatpuré, konserver |
| 🍷 | Alkohol | rött/vitt vin, öl, sprit till matlagning |
| 🧂 | Staples (kontrollera hemma) | salt, peppar, lagerblad, ättika, socker, basoljor, kryddor man troligen redan har |

Faller något utanför, lägg det under **🛒 Övrigt**.

**Staples-regeln:** Om det är något som troligen finns hemma (salt, peppar, vetemjöl, olivolja, ättika, lagerblad, vanliga torrkryddor), lägg det under "Staples (kontrollera hemma)" istället för att tvinga in det i "Skafferi / torrt". Det minimerar onödig tid i butiken.

### Steg 5 — Preview i chatten

Visa listan i chatten innan du sparar. Format:

```
📝 INKÖPSLISTA — PREVIEW
═══════════════════════════════════

Titel: [förslag]
Datum: [YYYY-MM-DD]
Recept: [kommaseparerade]

Antaganden / val:
  - [t.ex. portioner per recept]
  - [t.ex. rotfruktskombo för Poulet rôti]

──────────────

🥩 Kött & fågel
  - [item] — [mängd] [(kommentar)]

🥕 Frukt & grönt
  - [item] — [mängd]

[...etc per kategori...]

═══════════════════════════════════
Säg "spara" för att skriva till Notion,
eller ge feedback för att justera (t.ex.
"dubbla schnitzeln", "byt rotfrukter mot pumpa+morot+rödlök").
```

### Steg 6 — Spara i Notion

När Nils säger **"spara"** (eller "skapa", "kör", "lägg till"):

1. Bygg page-content som markdown (se format nedan).
2. Anropa `notion-create-pages` med:
   - `parent`: `{type: "data_source_id", data_source_id: "6988ad6c-4c42-4a4d-83fa-2d91bda0c965"}`
   - `properties.Titel`: titeln
   - `properties.Status`: "Att handla"
   - `properties["date:Datum:start"]`: ISO-datum (idag)
   - `properties.Recept`: kommaseparerad lista
   - `properties.Anteckningar`: antaganden
   - `content`: markdown-formaterad lista
3. Bekräfta med en länk:

```
✅ Sparat! Inköpslista — [titel]
   [Öppna i Notion]([url])
```

## Page content-format (markdown)

Notion-create-pages tar markdown. Använd headers per kategori, bullet-lista för items:

```markdown
## 🥩 Kött & fågel

- 2 fläskkotletter utan ben *(schnitzel)*
- 2 kg märgben, gärna grovt kluvna *(fond)*
- 1 hel kyckling, ca 1,5 kg *(poulet rôti — helst majskyckling)*

## 🥕 Frukt & grönt

- 2 citroner *(1 schnitzel + 1 poulet)*
- 1 gurka *(gurksallad)*
- ...

## 🌿 Färska örter

- 1 knippe persilja
- 1 knippe dill
- 1 kruka färsk timjan

## 🥚 Mejeri & ägg

- 2 ägg
- ~250 g smör
- ...

## 🥫 Skafferi / torrt

- Ströbröd, 150 g
- ...

## 🍷 Alkohol

- 1 flaska torrt rödvin
- ...

## 🧂 Staples — kolla att du har

Flingsalt, vanligt salt, svartpepparkorn, ättika, strösocker, lagerblad, herbes de Provence.

---

## Tips inför helgen

[Eventuella matlagnings-/timing-tips relevanta för rätterna, t.ex. att fonden tar 8–12 h, kycklingen ska torrsaltas dagen innan, etc.]
```

Lägg in tips om timing/förberedelser sist om det är relevant — det är värdefullt när flera rätter ska planeras.

## Konventioner och regler

- **Visa alltid preview innan spara** — skriv aldrig till Notion utan bekräftelse.
- **Konsolidera alltid dubbletter.** Två "1 citron" blir "2 citroner".
- **Notera ursprung** per ingrediens i parentes — gör det lätt att förstå varför just denna mängd.
- **Var generös med staples-flaggning.** Bättre att markera något som "staple, kolla hemma" än att tvinga ett extra köp av något Nils redan har.
- **Anteckna antaganden.** Om receptet är 2 portioner och Nils inte sagt något, skriv "Antar 2 portioner enligt receptets default" i Anteckningar-fältet — så är det dokumenterat och justerbart.
- **Datumförslag**: idag som default, men om Nils säger "för helgen" och idag är en torsdag/fredag, föreslå kommande lördag.
- **Titel-mönster**: `Inköpslista — <Recept1> + <Recept2> + ...` (kort), eller `Inköpslista — <YYYY-MM-DD>` om listan är generisk.
- **Status sätts till "Att handla"** vid skapande. Användaren markerar manuellt som "Handlad" i Notion efteråt.

## Vad denna skill INTE gör

- Skriver inte till SQLite-databasen (recept-DB:n). Detta är rent Notion.
- Hanterar inte automatisk avbockning eller sync mot något annat system.
- Genererar inte recept — för det, använd `recipe`-skillen.
- Ersätter inte den planerade Flask-baserade inköpslista-funktionen i webbsidan (Fas 5 i WORKFLOW_OVERHAUL_PLAN). Det är två kompletterande verktyg: webben för "klick-och-välj från recept-DB:n", chatten för "berätta vad du ska laga".
