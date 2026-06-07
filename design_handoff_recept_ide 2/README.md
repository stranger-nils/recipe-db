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
**Hög fidelity (hifi).** Färger, typografi, spacing, kantradier och interaktioner är genomarbetade och avsedda att återskapas pixel-nära. Designriktningen är **tunn, utilitär mono med industriell robusthet** — tänk **"JIRA/DevOps för kockar"**: sval-neutral grafit på off-white, **en enda monospace-familj** (IBM Plex Mono som standard) i **lätta vikter (400, max 500)** för *allt*, **raka hörn (0px)**, **kompakt densitet**, och en **industriell cyan** accent (DevOps-/märklappskänsla) som gör färgjobbet. Medvetet **tunt, lättläst och oputsat** — inga 700-vikter. Mål: ett vasst, robust internt verktyg.

**Nedtonat / linjer istället för boxar.** Gränssnittet är medvetet **avskalat**. Hårlinjer, cell-/radkanter och panel-/flikkanter är borttagna; separation sker via vityta, bakgrundsnyanser och en mycket subtil zebra (ingredienstabellen). **Fyllda "boxar" (chips, taggar, badges, sökfält, väljare, knappar) är utbytta mot linje-/underline-behandling**: sökfält och versionsväljare/ghost-knappar visas som **understrukna fält** (1px nederkant, accent vid fokus), `SKAFFERI`-taggar som **understrukna små versaler**, "Används i"-recept och receptchips som **textlänkar med underline**, versionsbadgen (v3) som **ren accenttext** utan platta. Inline-fält i ingredienstabellen är osynliga i vila och får en **underline** vid hover/fokus. Kvar som "box" är genuina kontroller (kryssrutor) **samt avsiktliga märklapps-taggar**: versionskoder (solid accent-platta) och `SKAFFERI`-flaggor (1px outline). Accentens vänsterstaplar (versionsnotis, anteckningar) behålls.

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
- **Aktivitetsrad (rail):** **mörk petrol** (härledd ur accenten, se tokens — inte svart), tre navknappar (Recept / Ingredienser / Planering). Ikoner: **uppslagen kokbok**, **mason jar** (ingrediensförvaring) och **planerings-checklista** — minimala streck-SVG (tunn linje, `stroke 1.25`, size 21) i `app/ui.jsx`. Aktiv knapp: ljus glyf + 3px **vit** stapel till vänster. Tooltip på hover. Ingen logotyp.
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
Alla färger i **oklch** — sval-neutral grafit (hue ~250–256) med en aning värme i mitttonerna, **inte** iskall. Accenten är en bestämd, vuxen arbetsblå som ensam bär färgjobbet.

### Färg (CSS-variabler på `:root`)
| Token | Värde (oklch) | Ungefärlig hex | Användning |
|---|---|---|---|
| `--paper` | `oklch(0.994 0.002 250)` | `#fdfdfe` | Editor-/dokumentbakgrund |
| `--bg` | `oklch(0.966 0.0035 248)` | `#f3f3f5` | Chrome: flikrad, chips, inputs |
| `--panel` | `oklch(0.978 0.003 248)` | `#f6f6f8` | Sidopanel |
| `--rail` | *härledd* | — | Aktivitetsrad + statusrad. **Härleds ur accenten** på `.ide`: `color-mix(in oklab, var(--accent) 52%, oklch(0.205 0.03 216))` — en **mörk, mättad nyans av accenten** (hue-matchad bas) så spalten tydligt läser som accentfärgen och följer ljusare/mörkare val. |
| `--rail-fg` | *härledd* | — | Text/ikon på rail: `color-mix(in oklab, var(--accent) 36%, oklch(0.86 0.02 210))`. |
| `--ink` | `oklch(0.305 0.021 256)` | `#393f49` | Primär text |
| `--ink2` | `oklch(0.462 0.018 254)` | `#5e646e` | Sekundär text |
| `--ink3` | `oklch(0.620 0.014 252)` | `#868b94` | Tertiär/dämpad text |
| `--line` | `oklch(0.906 0.004 248)` | `#dde0e3` | Hårlinjer (rader) |
| `--line2` | `oklch(0.822 0.006 248)` | `#c4c7cc` | Starkare kanter, inputs |
| `--accent` | `#0f6f86` | `#0f6f86` | **Aptitlig blågrön petrol** (proffskök/fresh, en aning åt blått). Används **sparsamt** för: aktiv rad, länk-hover, primär-CTA, versionstaggar (v2/v3), och **härleder rail**. **OBS:** kvantiteter och stegnummer är **neutrala** (`--ink2`/`--ink3`), ej accent — medvetet för en lugnare/mindre putsad känsla. Accenten är **djup nog (kontrast ≥4.5:1 på off-white)**. |

Accenten är en tweakbar token — en **ramp från djup petrol till ljus cyan-teal**: `#16859d`, `#1f9ab4`, `#2ab0c9` (ljusare), plus `#0d8267` (sjögrön). **Rail/statusrad följer automatiskt** vald accent (mörkare/ljusare). OBS: ljusare val sänker textkontrasten på små mono-siffror — default `#0f6f86` håller ≥4.5:1.

### Diff-färger (lugna, en aning kulör; åtskilda av markörer +/−/~)
| Token | Värde | |
|---|---|---|
| `--add-bg` | `oklch(0.957 0.024 158)` | tillagd rad (höger), markör `+` — svagt grön |
| `--add-fg` | `oklch(0.46 0.075 158)` | |
| `--del-bg` | `oklch(0.957 0.024 26)` | borttagen rad (vänster), markör `−`, genomstruken — svagt röd |
| `--del-fg` | `oklch(0.52 0.115 26)` | |
| `--chg-bg` | `oklch(0.957 0.022 252)` | ändrad rad, markör `~` — svagt blå |
| `--chg-fg` | `oklch(0.47 0.075 256)` | |

### Kantradier (raka — industriellt)
`--r-sm: 0px; --r-md: 0px; --r-lg: 0px;` Helt raka hörn genomgående för en utilitär, ostädad industrikänsla.

### Spacing / densitet
Densitet är en tweak; **kompakt är default** (tät, verktygsmässig). Variabler sätts per densitetsklass:
| Klass | `--fs` (brödtext) | `--u` (spacing-enhet) | `--lh` | `--tab-h` |
|---|---|---|---|---|
| `.dens-kompakt` (default) | 15px | 6px | 1.5 | 33px |
| `.dens-normal` | 17px | 8px | 1.62 | 38px |
| `.dens-luftig` | 19px | 11px | 1.78 | 42px |
Padding/marginaler uttrycks som `calc(var(--u) * n)`.

### Typografi (tweakbar; default = IBM Plex Mono)
- **En enda monospace-familj för allt**, i **lätta vikter** — målet är tunna, lättlästa bokstäver, inte en tjock konsol. Default `--serif` = `--mono` = **IBM Plex Mono**. Brödtext/UI **weight 400**; rubriker, småetiketter, kvantiteter och taggar **weight 500**. **Inga 700-vikter** någonstans.
- **Viktigt:** allt använder samma familj — även de VERSALA småetiketterna ("INGREDIENSER" m.fl.) är samma IBM Plex Mono, bara `text-transform:uppercase` + `letter-spacing:.04em` + weight 500. (Tidigare såg de ut som en annan font p.g.a. tung 700-vikt — undvik det.)
- Alternativa typsnitt (tweak): **JetBrains Mono** och **Space Mono** (bredare, mer typewriter). Alla tre monospace, alla laddas med lätta vikter (300/400/500).
- Rubriker (h1): **mono, weight 500, gemener**, `letter-spacing:-0.01em`. Recepttitel ~`1.55×`, vy-rubriker ~`1.45×` av brödtext.
- Versionskoder (v2/v3, ver-notistagg) renderas som **solida accent-etikett-taggar** (paper-text på blå, weight 500). `SKAFFERI`-flaggor är **outline-taggar** (1px ram, raka hörn).
- Default-densitet: **kompakt** (`--fs:15px`).

Google Fonts som laddas: **IBM Plex Mono** (300/400/500), **JetBrains Mono**, **Space Mono**.

---

## Screens / Views

### 1. Recept (öppet recept i flik)
**Syfte:** läsa/laga ett recept; växla version; jämföra versioner; lägga minnesanteckningar.

**Explorer (sidopanel) — filträd:**
- Header: etikett "Recept" (mono, gemener) + en `<select>` för **gruppering**: `efter kök` / `efter kategori` / `A–Ö`.
- Sökfält (mono): filtrerar på titel + kök, med sökikon.
- Trädet: **kollapsbara grupprubriker** (mono VERSALER **11px**, t.ex. "ASIATISKT") — chevron till vänster (pekar ned = öppen, höger = kollapsad), antal till höger; klick på rubriken fäller in/ut gruppens rader. Kollapsläge hålls i klient-state (`collapsed`-Set, namespace per vy). **Recept-rader: mindre än gruppen (10.5px), indenterade ett steg (padding-left 24px)** och avskilda med en **svag understrykning per rad** (`color-mix(var(--line) 55%, transparent)`) för tydlig separation. Rad = receptnamn; recept med >1 version visar **solid v-tagg** (accent) till höger. **Aktiv rad: accent-tint + 2px accent vänster-kant** (vald-fil/ticket-markör) + accent-namn.

**Dokument (editor-body), max-bredd 760px, centrerat:**
- **Breadcrumb** (visas i ide-nivå "tydlig"/"nördig"): mono, `kök › slug.recept   @v3`.
- **H1** rättsnamn (systemfont 700, gemener).
- **Beskrivning** (serif, `--ink2`, max ~62ch).
- **Metarad:** "chips" (boxar, mono 11.5px, `--bg`-fyllda, 1px kant, raka hörn): Kök · Kategori · Tid · Portioner. Inga ikoner.
- **Versionsrad** (1px över/under-kant): vänster = versionsväljare (`<select>` i en box, mono) + knapp **"Jämför versioner"** (ghost-knapp; visas bara om recept har >1 version). Höger = **portions-stepper** (`– N port +`) som **skalar alla kvantiteter** med faktor `valda/bas-portioner`.
- **Versionsnotis** (om versionen har en `note`): citatblock med 2px accent-vänsterkant, serif kursiv, liten mono-tagg med versionsetikett.
- **Ingredienser** (sektion): lista där varje rad är ett grid `62px | 50px | 1fr` = **kvantitet** (mono, **neutral `--ink2`** — ej accent, för en lugnare/mindre putsad känsla, högerställd) | **enhet** (mono, dämpad) | **namn** (serif). Ev. `, beredning` i kursiv dämpad.rsiv dämpad. Skafferivaror visar liten tagg "SKAFFERI" (mono 9.5px, VERSALER, 1px kant). 1px underkant per rad.
- **Tillvägagångssätt** (sektion): numrerad lista. Stegnummer (mono, **dämpad `--ink3`** — ej accent, "01", "02"…) visas i ide-nivå "tydlig"/"nördig". Stegtext serif.

**Minnesanteckningar (annoteringar)** — på **både ingredienser och steg**:
- Affordans: en diskret **alltid synlig** knapp till höger på varje rad (både ingredienser och steg) — **"+ anteckning"** (eller **"redigera"** om en notis finns). Plain text (systemfont 11px, ingen box), accent + underline vid hover. Den ligger i flytet (egen grid-kolumn på ingrediensrader, sista flex-barn på stegrader) så den aldrig överlappar innehåll.
- Klick → inline-`<input>` (mono) öppnas under raden, autofokus, placeholder "Minnesanteckning till nästa gång…". **Enter** sparar, **Esc** avbryter, **blur** sparar. Tom = ta bort.
- Visning: en "marginalkommentar" under raden — 2px accent-vänsterkant, mono `~0.72em`, `--ink2`. Klick på den öppnar redigering.
- **Persistens & nyckel:** sparas fristående från versioner i `localStorage` (`mise.annos.v1`), map `key → text`. Nyckelformat: ingrediens `"<recipeId>:<versionId>:<ingrediensnamn>"`, steg `"<recipeId>:<versionId>:step:<stegindex>"`. (I produktion: spara per användare/recept i backend; överväg om anteckning ska följa ingrediensen över alla versioner — nuvarande prototyp scope:ar per version.)

**Indentering av anteckningar:** ingrediens-anteckning vänstermarginal 112px (= 62+50, aligns under namnkolumnen); steg-anteckning ligger i en `step-main`-kolumn så den aligns under stegtexten.

### 1b. Versionsdiff (egen flik)
**Syfte:** se vad som ändrats mellan två versioner av ett recept (git-split-stil).
- Topprad (`--bg`): titel (systemfont 700, gemener) + "versionsjämförelse"; till höger räknare som **ren text** (ingen färgplatta): `+N tillagda`, `−N borttagna`, `~N ändrade` (mono).
- Kolumnrubriker (sticky): två kolumner "VÄNSTER" / "HÖGER", var sin versionsväljare + datum. Defaultval: vänster = versionen före den man kom ifrån, höger = den man kom ifrån (eller aktuell).
- Ev. notisrad: versionernas `note` sida vid sida.
- **Två sektioner:** "Ingredienser" och "Tillvägagångssätt". Varje är ett rutnät med två kolumner (`1fr 1fr`), rad för rad parvis. Varje cell: markör (`+`/`−`/`~`) + text.
  - Ingrediensdiff: alignas på ingrediensnamn → typ `add` (bara höger), `del` (bara vänster, **genomstruken** text), `chg` (samma namn, ändrad mängd/enhet/beredning — båda sidor gråfält), `same`.
  - Stegdiff: LCS-radjämförelse av stegtexter → `same`/`add`/`del`.
- Tom motpartscell: transparent. Mittlinje (1px) mellan kolumnerna.

### 2. Ingredienser (Ingrediensbibliotek)
**Syfte:** katalog över alla ingredienser (källan-till-sanning).
- **Explorer:** etikett "KATEGORIER" + sökfält (filtrerar namn/alias). Lista: "Alla" + varje kategori, med antal; aktiv kategori = accent-bakgrund. (Kategorier: Kött, Fisk & skaldjur, Frukt och grönt, Färska örter, Baljväxter, Mejeri, Kolhydrater, Konserver, Smaksättare.)
- **Innehåll:** H1 "Ingrediensbibliotek" (systemfont 700, gemener). Ingen beskrivningstext.
- **Tabell** (1px kant runt, raka hörn). Kolumner:
  - **Namn** (serif 15px)
  - **Kategori** (`<select>` per rad, mono)
  - **Default-enhet** (`<input>` per rad)
  - **Alias** (`<input>`, komma-sep. synonymer/felstavningar; placeholder "—")
  - **Används i** (bredd 185px): recepten som ingrediensen ingår i, visade som **boxar staplade vertikalt** (mono 11px, 1px kant, `--bg`-fyllda). Varje box är en **klickbar länk** som öppnar receptet i en flik (växlar till Recept-vyn). Hover: accentfärg + accent-kant. "–" om inga.
  - **Skafferi** (kryssruta-knapp; ifylld accent när på)
- Radhover: svag accent-bakgrund. Header: mono, gemener, `--bg`-bakgrund.
- Recept-IDs härleds genom att matcha ingrediensens namn mot receptens ingredienser (aktuell version).

### 3. Planering (tvåstegsflöde)
**Syfte:** skapa en inköpslista från valda recept; kopiera som ren text till t.ex. iPhone-anteckningar.

**Explorer — receptväljare** (samma gruppering/sök/**kollaps** som Recept-vyn):
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
- Footer: primärknapp **"Skapa inköpslista →"** (blå accent-fylld, systemfont; inaktiv om inget att handla) + not "X av Y redan hemma · Z att handla".

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
- Tweaks: `fontPair`, `density`, `accent`, **`case`** (versaler/normal/gemener — styr skiftläge; **default = `versaler`** (stämplade VERSAL-etiketter). `gemener` = hela gränssnittet gement (nördigt terminalläge — även rubriker, namn och formulärkontroller via `text-transform:lowercase`)), `ide` (subtil/tydlig/nördig). Rail-färgen härleds ur `accent`.

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
- Återskapa den **tunna, utilitära mono-känslan**: en enda monospace-familj (IBM Plex Mono) i lätta vikter (400/500, **inga 700**) för allt, raka hörn, kompakt densitet, sval-neutral grafit, **solida accent-märklappar** för versionskoder, och en **skrikig industri-blå** accent (inkl. primär-CTA). De VERSALA småetiketterna måste vara samma familj som brödtexten. Medvetet tunt och oputsat.
- Texten är **på svenska** genomgående.
- Anteckningar och "har hemma"-status bör i produktion lagras per användare i backend, inte localStorage.
- Diff-algoritmerna (LCS för steg, namn-alignment för ingredienser) finns i `app/ui.jsx` som referens.
- Använd er befintliga komponentbas/datalager — HTML-filerna är referens, inte kod att klistra in.
