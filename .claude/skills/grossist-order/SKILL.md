---
name: grossist-order
description: "Handla en inköpslista på Mathem i webbläsaren — slår upp varje vara, matchar mot rätt artikel och förpackningsstorlek, och fyller varukorgen. Slutför ALDRIG köpet; Nils klickar hem det själv. Triggas av /grossist-order eller fraser som 'handla listan', 'lägg i varukorgen', 'beställ maten', 'handla på Mathem', 'köp veckans varor'. Tar emot en lista från veckomeny-skillen, från /plan-fliken på receptsajten, eller klistrad i chatten."
---

<!-- SKILL_VERSION: 2026-08-30 -->

## ⚠️ Versionskontroll — gör detta först

Den här skillen finns i två kopior som uppdateras via **olika kanaler** och glider isär tyst:

- **Repot**: `recipe-db/.claude/skills/grossist-order/SKILL.md` — source of truth, versionerad i git.
- **Claude-kontot** (Customize → Skills) — det är den kopian Cowork laddar, och den uppdateras **bara** genom manuell uppladdning.

Kontrollera därför alltid vid start, innan du gör något annat:

1. Läs `SKILL_VERSION`-raden överst i den här filen — det är kopian du kör just nu.
2. Är `recipe-db` åtkomlig? Läs `SKILL_VERSION` överst i `.claude/skills/grossist-order/SKILL.md`.
3. **Är repot nyare** → följ repo-filen i den här sessionen och säg det rakt ut.
4. Går repot inte att läsa → nämn i en mening att versionskontrollen inte kunde göras.

Mappningsfilen (`references/mathem-mapping.json`) läses och skrivs **alltid i repot**, aldrig i kontokopian — den är skillens minne och måste versioneras i git.

# Grossist-order — fyll varukorgen på Mathem

## Profil
Läs `.claude/cowork-instructions.md` om den finns. Ton och samarbetsstil gäller här också, men var kort: det här är ett arbetspass, inte en matlagningsdiskussion.

## ⛔ Hårda gränser

1. **Du slutför aldrig ett köp.** Du stannar när varukorgen är fylld. Nils går till kassan själv, väljer leveranstid och betalar.
2. **Du loggar aldrig in.** Du skriver aldrig in e-post, lösenord, BankID, kort- eller adressuppgifter. Krävs inloggning: be Nils logga in i webbläsarrutan, vänta, och fortsätt sedan.
3. **Du ändrar inget på kontot** — inte leveransadress, inte betalsätt, inte prenumerationer, inte sparade listor.
4. **Du tömmer inte varukorgen.** Ligger det redan varor där: rapportera vad du ser och fråga innan du lägger till.

## Verktyg

Den inbyggda webbläsaren (`mcp__remote-devices__Claude_Browser__*`) är förstahandsvalet — den har en egen beständig profil, så en inloggning på Mathem sitter kvar mellan sessioner. Be Nils välja `claude-in-chrome` i stället om han hellre handlar i sin vanliga Chrome, där han redan är inloggad.

**Läs sidor med text, inte med ögon.** `get_page_text` ger produktnamn, förpackningsstorlek, märke, pris och jämförpris i klartext. `read_page` ger strukturen med `ref_N` att klicka på. Skärmdump behövs bara när något ser fel ut och du vill se varför — den kostar mycket och ger mindre.

## Så är Mathem byggd (verifierat 2026-08-30)

**Söksida:** `https://www.mathem.se/se/search?q=<urlencoded sökterm>`

Varje träff är en `article` vars tillgänglighetsnamn är `"<Produktnamn> - <storlek>"`, och den innehåller allt du behöver:

```
article "Pinjenötter - 100 g" [ref_448]
 link [ref_450] href="/se/products/49228-sellton-pinjenotter/"
 generic "100 g, Sellton" [ref_452]
 generic "75,67 kr" [ref_454]
 generic "756,70 kr /kg" [ref_455]
 button "Lägg till i varukorgen" [ref_456]
```

Tre konsekvenser som avgör hur du arbetar:

1. **Alla köpknappar heter likadant.** En `find` på "lägg till" ger tjugo identiska träffar utan att avslöja vilken som hör till vilken vara. Klicka **aldrig** på en knapp du hittat med `find` direkt.
2. **Rätt väg är via artikeln.** `find` på produktnamnet → ta `article`-referensen → `read_page` med `ref_id` satt till den → använd knappen som ligger *inuti* det svaret. Då kan du inte lägga fel vara i korgen.
3. **Produkt-URL:en är stabil** (`/se/products/49228-sellton-pinjenotter/`). Det är den du sparar i mappningen — nästa gång navigerar du rakt dit och slipper söka.

Slutsålda varor står som `Slut hos leverantör` i texten och saknar fungerande köpknapp.

**Efter första klicket byter kortet skepnad.** Köpknappen blir en stegare:

```
button "Ta bort från varukorgen" [samma ref som förut]   ← minus
textbox "Antal" [ny ref]
button "Lägg till i varukorgen" [ny ref]                 ← plus
```

Behöver du fler än en: **klicka plusknappen en gång per extra förpackning.** Att sätta
`Antal`-fältet med `form_input` ser ut att lyckas men registreras inte av sidan — värdet
skrivs, korgen ändras inte, och felet syns först i varukorgen. Verifierat 2026-08-30.

Läs om artikeln efter första klicket för att få plusknappens ref — den finns inte förrän
varan ligger i korgen.

## Mappningsfilen — skillens minne

`references/mathem-mapping.json` i repot. Den är hela poängen med skillen: första körningen är pratig, den femte är nästan tyst.

```json
{
  "schema_version": "1",
  "updated_at": "2026-08-30",
  "items": {
    "pinjenötter": {
      "query": "pinjenötter",
      "product_url": "/se/products/49228-sellton-pinjenotter/",
      "product_name": "Pinjenötter",
      "brand": "Sellton",
      "package": "100 g",
      "package_amount": 100,
      "package_unit": "g",
      "confirmed_at": "2026-08-30",
      "note": "billigast per kg av de icke-eko"
    }
  }
}
```

Nyckeln är ingrediensens **kanoniska namn i receptdatabasen**, gemener. Då matchar den rakt av mot det inköpslistan levererar.

## Arbetsflöde

### Steg 1 — Ta emot listan

Tre källor: veckomeny-skillen (i sessionen), `plans/<slug>.json` (läs och aggregera själv), eller klistrad text.

Varje rad behöver **namn, mängd och enhet**. Saknas mängd, fråga.

**Skafferivaror hoppas över som standard.** Listan markerar dem redan (`kitchen_staple`) — salt, peppar, olja, vanliga torrkryddor. Fråga en gång i början: *"Jag hoppar över de 19 skafferivarorna. Är det något där du faktiskt behöver fylla på?"*

### Steg 2 — Öppna och kontrollera läget

Navigera till `https://www.mathem.se/`. Läs sidan:

- **Inte inloggad** → be Nils logga in i rutan. Vänta på hans klarsignal. Fortsätt inte utan.
- **Varor redan i korgen** → rapportera antal och fråga om de ska ligga kvar.

### Steg 3 — Per vara

1. **Slå upp i mappningen.** Finns varan → navigera direkt till `product_url`, kontrollera att den finns i lager och att priset inte flugit iväg, lägg i korgen. Klart, ingen fråga.
2. **Saknas den** → navigera till söksidan med varunamnet som `q`.
3. `get_page_text` för att se träffarna som text.
4. Välj kandidat efter reglerna nedan.
5. `find` på produktnamnet → `read_page` med artikelns `ref_id` → klicka artikelns egen köpknapp.
6. Kontrollera att korgen räknade upp innan du går vidare.

**Antal förpackningar** = behovet delat med förpackningsstorleken, uppåt. 500 g körsbärstomater med 250 g-askar = två klick på plusknappen (se stegaren ovan — inte `Antal`-fältet). Säg det i rapporten när det blir mer än en.

### Steg 4 — Matchningsregler

- **Namnet ska stämma på riktigt.** "Pinjenötter" matchar `Pinjenötter 100 g`. Det matchar inte `Pesto Genovese` — sökmotorn returnerar allt som *nämner* ordet, och de första träffarna är inte alltid varan du vill ha.
- **Minsta förpackning som täcker behovet.** Behöver du 40 g, ta 100 g-asken, inte 750 g-påsen.
- **Jämför per kilo** när två förpackningar båda duger. Jämförpriset står i texten.
- **Eko bara om Nils bett om det.** Annars billigaste rimliga alternativ av jämförbar kvalitet.
- **Färskvaror räknas i styck** där receptet gör det: "2 rödlök" är en lök-påse eller lösvikt, inte 2 kg.
- **Slut hos leverantör** → ta näst bästa träff och flagga bytet i rapporten.
- **Kött, fisk och ost är kvalitetsval**, inte pris. Är det oklart vilken kvalitet Nils vill ha — fråga.

### Steg 5 — Fråga eller avgör själv

**Avgör själv:** förpackningsstorlek, antal, uppenbart namnmatchande varumärke, billigaste av likvärdiga.

**Fråga Nils:**

- Ingen träff alls på varan.
- Bästa träffen är en tolkning, inte en matchning (t.ex. `rättika` → daikon vs svart rättika).
- Priset sticker ut jämfört med vad varan brukar kosta.
- Kvalitetsvalet spelar roll för rätten (kött, fisk, ost, olivolja).

Samla frågorna och ställ dem i klump när du gått igenom listan — avbryt inte var tredje vara.

### Steg 5b — Verifiera mot varukorgen

Gå till `/se/cart/` och läs den med `get_page_text` **innan** du rapporterar. Sidan behöver
ett par sekunder — får du bara rubriken "Varukorg", vänta och läs om.

Radpriset avslöjar antalet: en vara à 4,95 kr som står på 4,95 i korgen ligger där i ett
exemplar, inte två. Det är enda pålitliga sättet att upptäcka att en antalsändring inte gick
igenom. Rätta direkt i korgen — varje rad har samma stegare där.

### Steg 6 — Rapport

```
🛒 VARUKORG — Mathem
═══════════════════════════════════
Lagt i korgen: 31 av 34 varor · ca 1 240 kr

Avvikelser:
  - körsbärstomater: 250 g-askar, tog 2 st (behov 500 g)
  - rättika: fanns bara som daikon 300 g — dubbelt mot behovet
  - pecorino: slut hos leverantör, tog Pecorino Romano 150 g i stället

Kunde inte hittas (3):
  - citrongräs — inga färska träffar, finns fryst? säg till
  - ...

Ny i mappningen: 13 varor
═══════════════════════════════════
Korgen är fylld men INTE beställd.
Gå till kassan själv, välj leveranstid och betala.
```

### Steg 7 — Uppdatera mappningen

Skriv in varje vara du bekräftat i `references/mathem-mapping.json` med produkt-URL, storlek och dagens datum. Behåll `note` där du valde bort något uppenbart — nästa körning ska inte behöva göra om resonemanget.

Bytte Nils ut ett val du gjort: **skriv över posten med hans val.** Hans korrigering är mer värd än din första gissning.

## Vad den här skillen INTE gör

- Slutför inga köp, väljer ingen leveranstid, rör inga betaluppgifter.
- Loggar inte in och hanterar inga lösenord.
- Bygger inga inköpslistor (→ `veckomeny`, eller `/plan`-fliken på sajten).
- Skriver inte till receptdatabasen eller till Notion.
- Handlar inte på andra sajter. Ska en annan butik stödjas är det en egen sidostruktur-sektion och en egen mappningsfil.
