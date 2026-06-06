# Handoff: Recept-IDE (recept · ingredienser · planering)

## Overview
"mise" är en webbapp för att skriva, organisera och laga recept — utformad i gränslandet mellan **klassisk restaurangkokbok** och **programmerings-IDE**. Målgruppen är hemmakockar och proffskockar som värdesätter tydlig struktur utan fluff.

Appen har **tre vyer** som växlas via en aktivitetsrad till vänster:
1. **Recept** — recept öppnas i flikar (som filer i en editor); filträd i sidopanelen; versionsjämförelse (diff); löpande minnesanteckningar på ingredienser och steg.
2. **Ingredienser** — ett ingrediensbibliotek (katalog/"källan-till-sanning") som tabell.
3. **Planering** — ett tvåstegsflöde: inventering → inköpslista som kan kopieras som ren text.

## About the Design Files
Filerna i det här paketet är **designreferenser byggda i HTML/CSS + React (via in-browser Babel)** — en interaktiv prototyp som visar avsedd look och beteende. De är **inte produktionskod att kopiera rakt av**.

Uppgiften är att **återskapa dessa designer i målprojektets befintliga miljö** (t.ex. React/Vue/Svelte/SwiftUI) med dess etablerade mönster, komponenter och datalager. Finns ingen miljö ännu väljer du lämpligaste ramverk. Prototypen använder lokal mock-data (`data/recipes.js`) och `localStorage` för anteckningar — i produktion ska detta kopplas mot riktig datamodell/backend.

## Fidelity
**Hög fidelity (hifi).** Färger, typografi, spacing, kantradier och interaktioner är genomarbetade och avsedda att återskapas pixel-nära. Designen är medvetet **steril/industriell, nästan monokrom** (grafit på off-white), med raka hörn och hårlinjer — "proffsig restaurangsköksdokumentation", inte "modern AI-IDE".

---

## Global layout (skalet)
Ett helskärms-IDE-skal i CSS grid, tre kolumner + innehåll:

```
┌──────┬─────────────┬───────────────────────────────┐
│ rail │  explorer   │  editor                        │
│ 56px │ 220–300px   │  tabstrip (höjd ~33px kompakt) │
│      │ (sidopanel) │  ├─ editor-body (scroll)       │
│      │             │  └─ statusbar (26px)           │
└──────┴─────────────┴───────────────────────────────┘
```
- **Grid:** `grid-template-columns: 56px clamp(220px, 22vw, 300px) 1fr; height: 100vh; overflow: hidden;`
- **Aktivitetsrad (rail):** mörk grafit (`--rail`), tre navknappar (Recept / Ingredienser / Planering). Aktiv knapp: ljus glyf + 3px accent-stapel till vänster. Tooltip på hover (mono, mörk bubbla). Ingen logotyp.
- **Explorer (sidopanel):** byter innehåll per vy (se nedan). `background: var(--panel)`, 1px höger-kant.
- **Editor:** flikstrip överst, scrollande body, statusrad nederst.
- **Statusrad:** mörk grafit, mono 11px. Visar: vy-namn (kapitäl), aktuell version ("v3"), kök · tid (för recept) eller antal (övriga), höger: `ide: <nivå>` och `⌘K`.

### Flikar (tabstrip)
- Bara i **Recept**-vyn finns flera flikar (öppnade recept + ev. diff-flik). Ingredienser/Planering visar en enda fast, ej stängbar "flik" med vyns namn.
- Flik: mono 12px, 1px högerkant, aktiv flik har `background: var(--paper)` + 2px accent-linje i överkant. Stäng-kryss (×) till höger på icke-fasta flikar (18×18, hover ljus bakgrund).
- Recept öppnas som flik från filträdet, från kommandopaletten (⌘K), eller via länk i ingrediensbiblioteket. Diff öppnas som egen flik från receptet.

### Kommandopalett (⌘K / Ctrl+K)
Overlay (mörkt halvtransparent + blur), centrerad box (560px, raka hörn). Sökfält (serif 18px) + sökikon; live-filtrerade recept (max 8), Enter öppnar första träffen, Esc stänger. Klick utanför stänger.

---

## Design Tokens
Alla färger i **oklch** (kall, nästan avmättad gråskala). Accent är medvetet nära bläcket → näst intill monokromt.

### Färg (CSS-variabler på `:root`)
| Token | Värde (oklch) | Ungefärlig hex | Användning |
|---|---|---|---|
| `--paper` | `oklch(0.993 0.001 250)` | `#fdfdfd` | Editor-/dokumentbakgrund |
| `--bg` | `oklch(0.955 0.002 250)` | `#f0f0f1` | Chrome: flikrad, chips, inputs |
| `--panel` | `oklch(0.970 0.002 250)` | `#f4f4f5` | Sidopanel |
| `--rail` | `oklch(0.235 0.004 250)` | `#33363a` | Aktivitetsrad + statusrad |
| `--rail-fg` | `oklch(0.68 0.003 250)` | `#9a9c9f` | Text/ikon på rail |
| `--ink` | `oklch(0.215 0.004 250)` | `#2e3034` | Primär text, mörka knappar |
| `--ink2` | `oklch(0.415 0.004 250)` | `#5f6266` | Sekundär text |
| `--ink3` | `oklch(0.575 0.003 250)` | `#878a8d` | Tertiär/dämpad text |
| `--line` | `oklch(0.890 0.002 250)` | `#dcdcde` | Hårlinjer (rader) |
| `--line2` | `oklch(0.800 0.003 250)` | `#c2c3c6` | Starkare kanter, inputs |
| `--accent` | `#2f3e46` | `#2f3e46` | Accent (kvantiteter, aktiv, länk-hover) |

Accenten är en tweakbar token. Alternativ som erbjudits: `#3f6b73` (teal), `#454b54`, `#6a5040`, `#5c6b7a`.

### Diff-färger (ren gråskala, åtskilda av markörer +/−/~)
| Token | Värde | Hex | |
|---|---|---|---|
| `--add-bg` | `oklch(0.963 0 0)` | `#f3f3f3` | tillagd rad (höger), markör `+` |
| `--add-fg` | `oklch(0.30 0 0)` | `#454545` | |
| `--del-bg` | `oklch(0.910 0 0)` | `#e3e3e3` | borttagen rad (vänster), markör `−`, genomstruken text |
| `--del-fg` | `oklch(0.44 0 0)` | `#6e6e6e` | |
| `--chg-bg` | `oklch(0.948 0 0)` | `#efefef` | ändrad rad, markör `~` |
| `--chg-fg` | `oklch(0.30 0 0)` | `#454545` | |

### Kantradier (industriellt — i princip raka)
`--r-sm: 0px; --r-md: 0px; --r-lg: 0px;` (variabler finns kvar för enkel justering, men alla 0 i nuläget.)

### Spacing / densitet
Densitet är en tweak; **kompakt är default**. Variabler sätts per densitetsklass:
| Klass | `--fs` (brödtext) | `--u` (spacing-enhet) | `--lh` | `--tab-h` |
|---|---|---|---|---|
| `.dens-kompakt` (default) | 15px | 6px | 1.5 | 33px |
| `.dens-normal` | 17px | 8px | 1.62 | 38px |
| `.dens-luftig` | 19px | 11px | 1.78 | 42px |
Padding/marginaler uttrycks som `calc(var(--u) * n)`.

### Typografi (tweakbar; default = Spectral / IBM Plex Mono)
- `--serif`: **Spectral** (Google Fonts, vikter 400/500/600/700; även italic 400). Används för rubriker, recept-/ingrediensnamn, brödtext (instruktioner), beskrivningar.
- `--mono`: **IBM Plex Mono** (400/500/600). Används för all "chrome": flikar, filträd, etiketter, kvantiteter & enheter, koder, statusrad, knapptext, anteckningar.
- Rubriker (h1 för rättsnamn, "INGREDIENSBIBLIOTEK", "INVENTERING" m.fl.): **VERSALER**, weight 600, `letter-spacing: .012em`, font-size ≈ `calc(var(--fs) * 2.0)` för recepttitel, `~1.85×` för vy-rubriker.
- Sektionsetiketter ("INGREDIENSER", "TILLVÄGAGÅNGSSÄTT", kategorinamn): mono 11–12px, VERSALER, `letter-spacing: .08em`, `color: --ink3`, 1px underkant.
- Alternativa typsnittspar (tweak): `Archivo / IBM Plex Mono`, `IBM Plex Sans / IBM Plex Mono`.

Google Fonts som laddas: `Archivo`, `IBM Plex Sans`, `IBM Plex Mono`, `Spectral`.

---

## Screens / Views

### 1. Recept (öppet recept i flik)
**Syfte:** läsa/laga ett recept; växla version; jämföra versioner; lägga minnesanteckningar.

**Explorer (sidopanel) — filträd:**
- Header: etikett "RECEPT" (mono, VERSALER) + en `<select>` för **gruppering**: `efter kök` / `efter kategori` / `A–Ö`.
- Sökfält (mono): filtrerar på titel + kök, med sökikon.
- Trädet: grupprubriker (mono, t.ex. "Asiatiskt") med antal till höger; under varje grupp recept-rader. Rad = receptnamn (serif 13.5px); recept med >1 version visar badge "v2"/"v3" till höger. Aktiv rad: ljus accent-bakgrund + accentfärgad fet titel. Inga ikoner i trädet.

**Dokument (editor-body), max-bredd 760px, centrerat:**
- **Breadcrumb** (visas i ide-nivå "tydlig"/"nördig"): mono, `kök › slug.recept   @v3`.
- **H1** rättsnamn i VERSALER (serif 600).
- **Beskrivning** (serif, `--ink2`, max ~62ch).
- **Metarad:** "chips" (boxar, mono 11.5px, `--bg`-fyllda, 1px kant, raka hörn): Kök · Kategori · Tid · Portioner. Inga ikoner.
- **Versionsrad** (1px över/under-kant): vänster = versionsväljare (`<select>` i en box, mono) + knapp **"Jämför versioner"** (ghost-knapp; visas bara om recept har >1 version). Höger = **portions-stepper** (`– N port +`) som **skalar alla kvantiteter** med faktor `valda/bas-portioner`.
- **Versionsnotis** (om versionen har en `note`): citatblock med 2px accent-vänsterkant, serif kursiv, liten mono-tagg med versionsetikett.
- **Ingredienser** (sektion): lista där varje rad är ett grid `62px | 50px | 1fr` = **kvantitet** (mono, accent, högerställd) | **enhet** (mono, dämpad) | **namn** (serif). Ev. `, beredning` i kursiv dämpad. Skafferivaror visar liten tagg "SKAFFERI" (mono 9.5px, VERSALER, 1px kant). 1px underkant per rad.
- **Tillvägagångssätt** (sektion): numrerad lista. Stegnummer (mono, accent, "01", "02"…) visas i ide-nivå "tydlig"/"nördig". Stegtext serif.

**Minnesanteckningar (annoteringar)** — på **både ingredienser och steg**:
- Affordans: vid hover på raden visas en diskret knapp till höger — **"+ anteckning"** (eller **"redigera"** om en notis finns). Mono 10px, 1px kant, raka hörn, `--paper`-bakgrund.
- Klick → inline-`<input>` (mono) öppnas under raden, autofokus, placeholder "Minnesanteckning till nästa gång…". **Enter** sparar, **Esc** avbryter, **blur** sparar. Tom = ta bort.
- Visning: en "marginalkommentar" under raden — 2px accent-vänsterkant, mono `~0.72em`, `--ink2`. Klick på den öppnar redigering.
- **Persistens & nyckel:** sparas fristående från versioner i `localStorage` (`mise.annos.v1`), map `key → text`. Nyckelformat: ingrediens `"<recipeId>:<versionId>:<ingrediensnamn>"`, steg `"<recipeId>:<versionId>:step:<stegindex>"`. (I produktion: spara per användare/recept i backend; överväg om anteckning ska följa ingrediensen över alla versioner — nuvarande prototyp scope:ar per version.)

**Indentering av anteckningar:** ingrediens-anteckning vänstermarginal 112px (= 62+50, aligns under namnkolumnen); steg-anteckning ligger i en `step-main`-kolumn så den aligns under stegtexten.

### 1b. Versionsdiff (egen flik)
**Syfte:** se vad som ändrats mellan två versioner av ett recept (git-split-stil).
- Topprad (`--bg`): titel i VERSALER + "VERSIONSJÄMFÖRELSE"; till höger räknare som **ren text** (ingen färgplatta): `+N tillagda`, `−N borttagna`, `~N ändrade` (mono).
- Kolumnrubriker (sticky): två kolumner "VÄNSTER" / "HÖGER", var sin versionsväljare + datum. Defaultval: vänster = versionen före den man kom ifrån, höger = den man kom ifrån (eller aktuell).
- Ev. notisrad: versionernas `note` sida vid sida.
- **Två sektioner:** "Ingredienser" och "Tillvägagångssätt". Varje är ett rutnät med två kolumner (`1fr 1fr`), rad för rad parvis. Varje cell: markör (`+`/`−`/`~`) + text.
  - Ingrediensdiff: alignas på ingrediensnamn → typ `add` (bara höger), `del` (bara vänster, **genomstruken** text), `chg` (samma namn, ändrad mängd/enhet/beredning — båda sidor gråfält), `same`.
  - Stegdiff: LCS-radjämförelse av stegtexter → `same`/`add`/`del`.
- Tom motpartscell: transparent. Mittlinje (1px) mellan kolumnerna.

### 2. Ingredienser (Ingrediensbibliotek)
**Syfte:** katalog över alla ingredienser (källan-till-sanning).
- **Explorer:** etikett "KATEGORIER" + sökfält (filtrerar namn/alias). Lista: "Alla" + varje kategori, med antal; aktiv kategori = accent-bakgrund. (Kategorier: Kött, Fisk & skaldjur, Frukt och grönt, Färska örter, Baljväxter, Mejeri, Kolhydrater, Konserver, Smaksättare.)
- **Innehåll:** H1 "INGREDIENSBIBLIOTEK" (VERSALER). Ingen beskrivningstext.
- **Tabell** (1px kant runt, raka hörn). Kolumner:
  - **Namn** (serif 15px)
  - **Kategori** (`<select>` per rad, mono)
  - **Default-enhet** (`<input>` per rad)
  - **Alias** (`<input>`, komma-sep. synonymer/felstavningar; placeholder "—")
  - **Används i** (bredd 185px): recepten som ingrediensen ingår i, visade som **boxar staplade vertikalt** (mono 11px, 1px kant, `--bg`-fyllda). Varje box är en **klickbar länk** som öppnar receptet i en flik (växlar till Recept-vyn). Hover: accentfärg + accent-kant. "–" om inga.
  - **Skafferi** (kryssruta-knapp; ifylld accent när på)
- Radhover: svag accent-bakgrund. Header: mono, VERSALER, `--bg`-bakgrund.
- Recept-IDs härleds genom att matcha ingrediensens namn mot receptens ingredienser (aktuell version).

### 3. Planering (tvåstegsflöde)
**Syfte:** skapa en inköpslista från valda recept; kopiera som ren text till t.ex. iPhone-anteckningar.

**Explorer — receptväljare** (samma gruppering/sök som Recept-vyn):
- Etikett "VÄLJ RECEPT" + grupperings-`<select>` (`efter kök` / `efter kategori` / `A–Ö`).
- Sökfält (titel + kök).
- Sub-rad: knapp **"rensa"** (avmarkerar alla) + räknare "N valda". (Ingen "alla"-knapp.)
- Grupperade recept-rader med **kryssruta** (16px, ifylld accent + bock vid val) + namn.

**Steg-indikator** (överst i innehållet): `1 Inventering — 2 Inköpslista` (mono; aktivt steg = mörk fylld siffra). Stegen är klickbara; steg 2 är inaktivt tills det finns något att handla. Receptchips visas under indikatorn.

**Steg 1 — Inventering:**
- H1 "INVENTERING". Undertext: "N ingredienser · M redan hemma".
- Instruktion (serif): "Bocka i det du redan har hemma — skafferivaror är förbockade. Resten hamnar på inköpslistan."
- **Aggregerad ingredienslista** från alla valda recept (aktuell version), summerad per (namn + enhet), **grupperad per kategori** i en flerkolumns-layout (CSS `column-width: 280px`).
- Varje rad: kryssruta (= "har hemma") + mängd/enhet (mono) + namn (serif). **Skafferivaror är förbockade** och dämpade; "SKAFFERI"-tagg visas.
  - Logik: `harHemma(item) = override[key] ?? item.pantry`. Toggla skriver override per `key = "<namn>|<enhet>"`. Så nya varor får skafferi-default automatiskt utan att skriva över manuella val.
- Footer: primärknapp **"Skapa inköpslista →"** (mörk fylld; inaktiv om inget att handla) + not "X av Y redan hemma · Z att handla".

**Steg 2 — Inköpslista:**
- H1 "INKÖPSLISTA". Undertext: "N varor att handla · M recept".
- Visar **bara varor som inte är "har hemma"**, grupperade per kategori (samma kolumnlayout). Varje rad: kryssruta (= bockad/handlad → genomstruken) + mängd/enhet + namn.
- Topp-höger: primärknapp **"Kopiera lista"** → lägger **ren text** på urklippet (`navigator.clipboard.writeText`, med textarea-fallback). Byter till **"Kopierat ✓"** i ~1,8 s. (Ingen "Skriv ut".)
- **Textformat som kopieras:**
  ```
  Inköpslista — <N> recept

  FRUKT OCH GRÖNT
  - 2 st grön chili
  - 1 st gul lök

  MEJERI
  - 2 dl grädde
  ```
  (kategorirubrik i VERSALER, sedan `- <mängd> <enhet> <namn>` per rad, tom rad mellan grupper.)

---

## Interactions & Behavior (sammanfattning)
- **Vy-växling:** aktivitetsraden byter `mode` (recept/ingredienser/planering) → byter både explorer-innehåll och editor-innehåll. Recept-flikarna bevaras när man lämnar och återvänder till Recept-vyn.
- **Öppna recept:** filträd, ⌘K-palett, eller "Används i"-länk i ingrediensbiblioteket → lägger till flik (om ej redan öppen) och fokuserar den.
- **Stäng flik:** ×; aktiv flik flyttas till närliggande.
- **Skalning:** portions-stepper multiplicerar kvantiteter; bråk visas snyggt (½, ¼, ⅓ …).
- **Diff:** öppnas som egen flik; två versionsväljare som styr jämförelsen.
- **Anteckningar:** hover-affordans, inline-edit, Enter/Esc/blur, localStorage-persistens.
- **Inventering→lista:** override-baserad "har hemma", skafferi förbockat; kopiera-knapp med bekräftelse.
- **Tangentbord:** ⌘K / Ctrl+K togglar kommandopaletten.
- **Hover-states genomgående:** länkar/rader får accentfärg + accent-kant; knappar mörknar/accentueras.

## State Management (i prototypen — översätt till app-state/datalager)
- `mode`: aktiv vy.
- `tabs[]` + `activeKey`: öppna recept-/diff-flikar (`r:<id>`, `d:<id>`).
- `grouping` / `query`: filträdets gruppering + sök (Recept-vyn).
- `planGrouping` / `planQuery`: receptväljarens gruppering + sök (Planering) — egen state.
- `catFilter`: vald kategori i ingrediensbiblioteket.
- `selIds` (Set): valda recept för planering.
- Inventering: `have` (override-map `key→bool`), `bought` (avbockade i steg 2), `step` ('inventory'|'list'), `copied`.
- `annos` (map, persisteras i `localStorage["mise.annos.v1"]`): minnesanteckningar.
- Tweaks: `fontPair`, `density`, `accent`, `ide` (subtil/tydlig/nördig) — påverkar typsnitt, spacing, accent och hur "IDE-mässig" receptvyn är (breadcrumb, radnummer, kod-stil).

## Datamodell (se `data/recipes.js`)
- **Recept:** `{ id, slug, title, cuisine (kök), category, time, desc, versions[] }`.
- **Version:** `{ id, label ("v1"), date, servings, current?, note, ingredients[], steps[] }`.
- **Ingrediensrad:** `{ qty, unit, name, cat (ingredienskategori), pantry (skafferi), note (beredning) }`.
- **Steg:** sträng.
- **Katalog (bibliotek):** `[{ name, cat, unit, aliases, pantry }]`.
- **Kategorier:** lista i butiks-/avdelningsordning (driver gruppering i inköpslistan).
> Mock-datan är exempel byggd från användarens MVP — ersätt med riktig data.

## Assets
Inga bild-/ikonassets krävs. Den lilla ikonuppsättning som finns (nav-glyfer, sök, bock, ×, chevron) är enkla inline-SVG-streck i `app/ui.jsx`. Ikoner används medvetet sparsamt — endast navigation, sök, kryssrutor, flikstängning och breadcrumb-separator. Inga emoji.

## Files (i detta paket)
- `Recept-IDE.html` — huvudfil: all CSS (design tokens, layout, komponentstilar, print) + skript-laddning.
- `app/ui.jsx` — hjälpare (cx, fmtQty, currentVersion, diff-algoritmer) + ikoner + småkomponenter.
- `app/recipe.jsx` — `RecipeView` (recept + skalning + anteckningar) och `DiffView` (versionsdiff).
- `app/tools.jsx` — `IngredientView` (bibliotek) och `PlannerView` (tvåstegs planering).
- `app/shell.jsx` — skal: aktivitetsrad, explorer (alla vyer), flikstrip, statusrad, kommandopalett, `App`, tweaks-panel, mount + `TWEAK_DEFAULTS`.
- `data/recipes.js` — mock-data (recept, katalog, kategorier).
- `tweaks-panel.jsx` — tweak-panelens infrastruktur (kan utelämnas i produktion; tweaks motsvarar tema-/inställningsval).

## Att tänka på vid implementation
- Återskapa den **sterila, nästan monokroma** känslan: håll accenten nära bläcket, raka hörn, hårlinjer, VERSALA rubriker, mono till all "chrome" och serif till innehåll.
- Texten är **på svenska** genomgående.
- Anteckningar och "har hemma"-status bör i produktion lagras per användare i backend, inte localStorage.
- Diff-algoritmerna (LCS för steg, namn-alignment för ingredienser) finns i `app/ui.jsx` som referens.
- Använd er befintliga komponentbas/datalager — HTML-filerna är referens, inte kod att klistra in.
