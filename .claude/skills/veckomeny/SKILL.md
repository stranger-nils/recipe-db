---
name: veckomeny
description: "Planera veckans matlagning: föreslå ett bestämt antal maträtter utifrån önskemål, publicera dem som en HTML-sida på Raspberry Pi:n (nås över tailnet), och generera en komplett inköpslista när urvalet är klart. Triggas av /veckomeny eller fraser som 'veckomeny', 'veckans middagar', 'planera veckan', 'vad ska jag laga i veckan', 'matsedel', 'fem rätter till veckan'. Skriver ALDRIG till receptdatabasen — för att spara ett recept, använd recipe-skillen."
---

<!-- SKILL_VERSION: 2026-08-30 -->

## ⚠️ Versionskontroll — gör detta först

Den här skillen finns i två kopior som uppdateras via **olika kanaler** och glider isär tyst:

- **Repot**: `recipe-db/.claude/skills/veckomeny/SKILL.md` — source of truth, versionerad i git.
- **Claude-kontot** (Customize → Skills) — det är den kopian Cowork laddar, och den uppdateras **bara** genom manuell uppladdning.

Kontrollera därför alltid vid start, innan du gör något annat:

1. Läs `SKILL_VERSION`-raden överst i den här filen — det är kopian du kör just nu.
2. Är `recipe-db` åtkomlig (Cowork: ansluten mapp, Claude Code: repo-roten)? Läs `SKILL_VERSION` överst i `.claude/skills/veckomeny/SKILL.md`.
3. **Är repot nyare** → följ repo-filen i den här sessionen, och säg det rakt ut till användaren:
   > "Kontots skill-kopia är daterad `<kontots datum>`, repot har `<repots datum>`. Jag följer repo-versionen. Ladda upp den nya filen under Customize → Skills så försvinner glappet."
4. Går repot inte att läsa → nämn i en mening att versionskontrollen inte kunde göras.

Hoppa aldrig över steget. Det kostar två filläsningar och är enda skyddet mot att köra en månadsgammal instruktion utan att märka det.

# Veckomeny — planera veckan, publicera sidan, bygg inköpslistan

## Profil
Läs `.claude/cowork-instructions.md` om den finns. Den definierar ton och samarbetsstil. Följ den — du är kockmentorn här också, inte en menygenerator.

## Syfte

Nils säger hur många rätter han vill laga och vad han är sugen på. Du komponerar veckan, publicerar den som en sida han når från telefonen över tailnetet, och när han är nöjd bygger du inköpslistan.

**Tre hårda gränser:**

1. **Du skriver aldrig till receptdatabasen.** Inte ens för recept han gillar. Vill han spara ett → `recipe`-skillen tar över (Steg 10).
2. **Du skriver aldrig till Notion.** Inköpslistan bor på veckomeny-sidan.
3. **Du hittar aldrig på ingrediensdata.** `grocery_category` och `kitchen_staple` styr hur inköpslistan grupperas — de hämtas från prod eller väljs medvetet ur den tillåtna listan, aldrig ur minnet.

## Var saker ligger

| Vad | Var |
|---|---|
| Plandata | `<repo>/plans/<slug>.json` |
| Renderad sida | `<repo>/plans/<slug>.html` (+ `index.html`) |
| Renderare | `<repo>/scripts/build_plan_page.py` |
| Publicering | `<repo>/scripts/publish-plan.sh` (körs från Macen, **inte** från Cowork) |
| Publik adress | `$VECKOMENY_URL/<slug>.html`, default `https://nils-rpi:8443/...` (tailnet; 443 upptas av OpenClaw) |

**Hitta repo-roten** (fungerar i båda miljöerna):

```bash
REPO="$(ls -d "$HOME"/mnt/recipe-db /sessions/*/mnt/recipe-db "$HOME"/recipe-db 2>/dev/null | head -1)"
[ -n "$REPO" ] || echo "REPO_SAKNAS"
```

**Sourca API-konfig:**

```bash
set -a; [ -f "$REPO/.claude/.env" ] && source "$REPO/.claude/.env"; set +a
[ -n "$RECIPE_API_URL" ] && [ -n "$RECIPE_API_TOKEN" ] || echo "NO_API_CONFIG"
```

Utan API-konfig kan du fortfarande föreslå *nya* recept, men inte hämta befintliga eller matcha ingredienser mot katalogen. Säg det rakt ut och fortsätt — flagga i previewen att kategoriseringen är best-effort.

---

## Steg 1 — Ramarna

Du behöver tre saker innan du komponerar. **Fråga om något är oklart — gissa inte.**

1. **Antal rätter.** Framgår oftast ("fem middagar till veckan").
2. **Önskemål.** Sugen på något särskilt? Något som ska undvikas? Vardagsfart eller helgprojekt? Har han råvaror hemma som ska gå åt?
3. **Källa — det viktigaste valet:**
   - **Befintliga** — plocka ur receptdatabasen. Han vill laga sådant han redan har kurerat.
   - **Nya** — komponera nya rätter. Han vill utveckla repertoaren.
   - **Mix** — t.ex. tre trygga ur databasen + två nya att prova.

Framgår källan inte av hur han formulerar sig, **fråga rakt ut**: *"Vill du att jag plockar ur databasen, komponerar nytt, eller blandar?"* Formuleringar som "handla för recepten jag har" betyder befintliga; "hitta på något nytt" betyder nya; "fem middagar till veckan" är oklart — fråga.

> ⚠️ **"Mix" betyder variation, inte källa.** När Nils säger "ge en bra mix" eller "mixa så jag får både snabbt och mer avancerat" talar han om veckans sammansättning — kök, tekniker, svårighetsgrad. Det är **inte** ett svar på källfrågan. Läs aldrig in "några ur databasen + några nya" i ordet mix; källan är besvarad först när han sagt databas, nytt eller blandat i klartext.

Portioner: fråga inte varje gång. Anta **4 portioner** och skriv det i previewen så han kan invända.

---

## Steg 2 — Underlag från prod

Hämta alltid, innan du föreslår något (kräver API-konfig):

```bash
# Alla recept, med kitchen/type — underlag för urval och för variation
curl -sS -H "Authorization: Bearer $RECIPE_API_TOKEN" "$RECIPE_API_URL/api/recipe/search?q="

# Vad som lagats nyligen — så du inte föreslår samma sak vecka efter vecka
SINCE=$(python3 -c "import datetime,os; w=int(os.environ.get('VECKOMENY_REPEAT_WEEKS','3')); print((datetime.date.today()-datetime.timedelta(weeks=w)).isoformat())")
curl -sS -H "Authorization: Bearer $RECIPE_API_TOKEN" "$RECIPE_API_URL/api/cook-log?since=$SINCE"
```

**Upprepningströskeln** är `VECKOMENY_REPEAT_WEEKS` i `.claude/.env`, default **3 veckor**. Recept som lagats inom fönstret föreslås inte — om inte Nils ber om dem, eller uttryckligen vill ha en favorit i repris. Nämn det när du väljer bort något han kanske väntade sig: *"Chow mein hoppade jag över — du lagade den för två veckor sedan. Säg till om du vill ha den ändå."*

Svarar `/api/cook-log` med **404 eller 405** är GET-endpointen inte utrullad på VPS:en än (405 = bara POST finns där, dvs. koden är skriven men inte deployad). Fortsätt utan filtret och nämn det i en mening.

För varje recept du väljer ur databasen: hämta det fullständigt med `GET /api/recipe/<id>` — du behöver ingredienserna med `grocery_category` och `kitchen_staple` för inköpslistan.

---

## Steg 3 — Skissa veckan

Här komponerar du, men **skriver inga fullständiga recept**. Du behöver bara veta vad varje rätt är, ungefär hur den lagas, och varför den hör hemma i veckan.

En vecka är inte fem orelaterade recept. Tänk som någon som faktiskt ska laga dem:

- **Variation i kök och teknik.** Inte tre wokrätter. Sprid `kitchen` och `type`.
- **Belastning över veckan.** Om något tar tre timmar — säg det, och lägg resten av veckan lättare. Markera vad som är vardagsmat och vad som är helgprojekt.
- **Råvaruöverlapp är en fördel, inte ett fel.** Ett knippe koriander som går åt i två rätter slår två halva knippen som möglar. Nämn överlappen — de gör inköpslistan billigare.
- **Ett lärande per vecka.** Enligt profilen: minst en rätt ska lära honom något.

---

## Steg 4 — Kortförslag i chatten ⛔ GRIND

**Detta är en spärr, inte en formalitet.** Innan Nils godkänt får du inte skriva fullständiga recept, inte skapa `plans/<slug>.json`, inte rendera och inte publicera. Han vill kunna säga "nej, byt ut trea" innan någon lagt tid på en ingredienslista.

Presentera varje rätt på **två–tre rader**: titel, kök, tid, en mening om vad rätten är, och en kort märkning (snabb / mer hantverk, barnvänlig, vilken färsk ört den drar).

```
🗓  VECKOMENY v36 · 31 aug – 6 sep — 4 portioner
═══════════════════════════════════════════════
Källa: alla nya · Variation: fem olika kök

1. [Titel]                        🇻🇳 · 30 min · snabb · barnvänlig
   En mening om vad rätten är och vad som gör den värd att laga.

2. [Titel]                        🇮🇹 · 50 min · mer hantverk · basilika
   En mening.

...

Så hänger veckan ihop: [överlapp, belastning, vad som lär honom något]
═══════════════════════════════════════════════
Säg vad du vill ändra. När du är nöjd säger du "kör"
så skriver jag ut recepten, bygger sidan och publicerar.
```

Sedan **väntar du**. Han justerar — byter ut rätter, ändrar riktning, ber om en till vegetarisk. Iterera på den här nivån så många varv som behövs; det kostar nästan ingenting jämfört med att skriva om fem fullständiga recept.

Godkännandet ska vara explicit: "kör", "publicera", "godkänt", "sätt igång". Ett "snyggt!" eller "det ser bra ut" är inte ett godkännande — fråga då om han vill att du kör.

---

## Steg 5 — Fullständiga recept, data och rendering

**Först nu** skriver du ut recepten i sin helhet.

För **nya** rätter: håll samma kvalitetsnivå som `recipe`-skillen kräver — komplett ingredienslista med mängd och enhet, numrerade instruktioner, autenticitet före förenkling. Skillnaden är att de inte kanoniseras hårt än; det görs först vid spar.

För rätter **ur databasen**: hämta dem fullständigt med `GET /api/recipe/<id>` — du behöver ingredienserna med `grocery_category` och `kitchen_staple` för inköpslistan.

**Ingrediensdata** — det här avgör om inköpslistan blir användbar:

1. Bygg ingredienskatalogen från prod (samma mönster som `recipe`-skillen: hämta alla recept, samla ingrediensnamn, `grocery_category`, `kitchen_staple`).
2. Finns ingrediensen → använd **kanoniskt namn** och **kopiera dess `grocery_category` och `kitchen_staple`**. Sätt `"new": false`.
3. Finns den inte → välj `grocery_category` ur den tillåtna listan nedan, sätt `kitchen_staple` (1 för skafferisaker: salt, peppar, olja, vanliga torrkryddor), och `"new": true`. Sidan markerar den som *ny* så Nils ser vad som inte finns i databasen än.

Tillåtna `grocery_category`-värden (fast lista, CHECK-constraint i DB:n):
`Frukt och grönt`, `Färska örter`, `Mejeri`, `Kött`, `Fågel`, `Fläsk`, `Fisk`, `Kolhydrater`, `Baljväxter`, `Konserver`, `Smaksättare`, `Färdiga tillbehör`, `Bageri`, `Frys`, `Alkohol`, `Övrigt`.

Sedan:

1. **Slug = ISO-veckan för den vecka som ska lagas**, inte veckan det är idag:

```bash
date -d "+4 days" +%G-w%V 2>/dev/null || date -v+4d +%G-w%V   # GNU / BSD
```

   Fyra dagars framförhållning ger rätt vecka oavsett när planeringen sker: mån–ons planerar man innevarande vecka, tors–sön nästa. Rakt `date +%G-w%V` ger fel svar varje söndag — då är det veckan som tar slut som föreslås. Stämmer det inte med vad Nils menar, fråga.

   Finns filen redan för samma vecka → **skriv över den** (samma URL, sidan uppdateras). Vill han ha en parallell variant → `2026-w36-b`.

2. Skriv `$REPO/plans/<slug>.json` enligt schemat nedan.
3. Rendera:

```bash
cd "$REPO" && python3 scripts/build_plan_page.py "plans/<slug>.json"
```

Renderaren äger utseendet — **skriv aldrig HTML själv**. Behöver sidan se annorlunda ut ändras `scripts/build_plan_page.py`, inte den här skillen.

---

## Steg 6 — Publicera till Pi:n

Cowork-sandboxen ligger **inte** på tailnetet och har inga ssh-nycklar — du kan inte pusha till Pi:n härifrån. Två vägar:

- **Autopublicering installerad** (`docs/autopublish.md`) → filen skickas av sig själv inom ~15 sekunder. Säg bara att den är på väg.
- **Annars** → be Nils köra:

```bash
cd ~/recipe-db && ./scripts/publish-plan.sh
```

Bekräfta så här:

```
✅ Veckomeny v36 renderad — 5 rätter
   https://nils-rpi:8443/2026-w36.html
   (kör ./scripts/publish-plan.sh om sidan inte dykt upp)
```

I Claude Code kan du köra `publish-plan.sh` själv.

---

## Steg 7 — Justeringar

Han kommer att vilja byta ut rätter även efter publicering. Är ändringen liten (en rätt byts, en tid justeras) — uppdatera JSON:en, rendera om, samma slug och samma URL. Ska halva veckan göras om: gå tillbaka till kortförslaget i Steg 4 och stäm av innan du skriver ut recepten igen. Sidan byts ut under honom — nämn att han kan behöva ladda om.

Sidan har egna reglage han sköter själv: han kan bocka ur en rätt direkt på sidan, och inköpslistan räknas om i webbläsaren. Be honom inte om en ny körning för sådant.

---

## Steg 8 — Inköpslistan

**Listan finns redan.** Renderaren bäddar in den i sidan under fliken *Inköpslista* — konsoliderad per vara, grupperad i butiksordning, med skafferivaror sist och avbockning som sparas i telefonen.

När Nils säger att han är nöjd:

1. Kontrollera att varje ingrediens i JSON:en har `grocery_category` och `kitchen_staple` — utan dem hamnar varor under *Övrigt* och listan blir sämre i butiken.
2. Rendera om.
3. Visa listan **också i chatten** (samma gruppering) så han kan reagera på antaganden: portioner, mängder som ser stora ut, sådant han troligen har hemma.
4. Notera antaganden uttryckligen: *"4 portioner rakt igenom. Jag räknade 700 g potatis till nr 2 och 4 tillsammans."*

Enheter som inte går att slå ihop (1 tsk + 1 st ingefära) redovisas bredvid varandra på **en** rad — det är en vara att köpa. Så gör sidan redan; gör likadant i chatten.

---

## Steg 9 — Handla

När listan sitter, erbjud att handla den: **invokera `grossist-order`-skillen** med listan som indata. Den sköter Mathem i webbläsaren, matchar varor mot artiklar och fyller varukorgen — och stannar där. Nils slutför alltid köpet själv.

Finns skillen inte i den här sessionen, säg det i en mening och erbjud listan att kopiera i stället (knappen *Kopiera* på sidan).

---

## Steg 10 — Spara ett recept han gillar

Säger han *"spara nr 3"* / *"den där pastan vill jag ha kvar"*:

> "Det där är `recipe`-skillens jobb — den kanoniserar ingredienserna mot prod och gör en riktig commit-preview. Jag lämnar över."

**Invokera `recipe`-skillen** med utkastet som underlag. Gör aldrig sparandet själv, inte ens genom att posta till `/api/recipe` — kanoniseringen och `kitchen`/`type`-reglerna bor där, och en genväg här ger skräpdata i databasen.

Efter sparandet: uppdatera rättens post i JSON:en till `"source": "db"` med `recipe_id` och `url`, och rendera om. Då pekar sidan på det riktiga receptet.

---

## Plan-JSON — schema

```json
{
  "schema_version": "1",
  "slug": "2026-w36",
  "week": "v36 · 31 aug – 6 sep",
  "title": "Veckomeny v36",
  "created_at": "2026-08-30T09:00:00Z",
  "note": "Önskemål: snabbt på vardagar, ett helgprojekt, inget fläsk.",
  "dishes": [
    {
      "id": "d1",
      "source": "db",
      "recipe_id": 20,
      "url": "https://recipedb.cloud/recipe/20",
      "title": "Chow mein med jätteräkor",
      "kitchen": "🥢 Kantonesiskt",
      "type": "Wok",
      "tags": "wok,snabbt",
      "servings": 4,
      "time": "30 min",
      "description": "…",
      "why": "Woken ska vara rykande het innan nudlarna går i — annars ångas de.",
      "instructions": "1. …\n2. …",
      "notes": null,
      "ingredients": [
        {
          "name": "jätteräkor",
          "amount": "250",
          "unit": "g",
          "note": "",
          "grocery_category": "Fisk",
          "kitchen_staple": 0,
          "new": false
        }
      ]
    }
  ]
}
```

**Fältregler:**

- `id` — unikt inom planen (`d1`, `d2`, …). Sidan använder det för val och localStorage; **byt aldrig id på en rätt som ligger kvar**, då tappar Nils sina bockningar.
- `source` — `"db"` eller `"draft"`. Styr märkningen på sidan.
- `url` — bara för `source: "db"`; `$RECIPE_API_URL/recipe/<id>`.
- `why` — en mening om vad rätten lär honom. Utelämna hellre än att fylla med floskler.
- `time`, `servings` — visas i metaraden. `servings` är per rätt, inte per vecka.
- `new` per ingrediens — `true` bara när den saknas i prod-katalogen.
- `amount` får vara tom (t.ex. salt efter smak). Enheter som `msk`, `klyfta`, `knippe` skrivs som i databasen.

---

## Regler

- **Kortförslag före detaljer, alltid.** Inga fullständiga recept, ingen JSON, ingen rendering och ingen publicering innan Nils godkänt förslagslistan i Steg 4.
- **"Mix" betyder variation**, inte att källan är blandad. Källan bekräftas i klartext.
- **Aldrig skrivning till recept-DB:n eller Notion.** Steg 10 är enda vägen till databasen, via `recipe`-skillen.
- **Prod är källan** för befintliga recept, ingredienskatalog, `kitchen`/`type` och cook-log. Lokal `recipe.db` är en gammal snapshot — använd den bara utan API-konfig, och flagga då att matchningen är best-effort.
- **Renderaren äger utseendet.** Skriv aldrig HTML i den här skillen.
- **Samma vecka = samma slug = samma URL.** Justeringar skriver över, de skapar inte en ny sida.
- **Stabila `id`:n** mellan omkörningar, annars nollställs Nils bockningar.
- **Redovisa antaganden** — portioner, mängder, uteslutna recept och varför.
- **Föreslå inte det han nyss lagat** utan att säga att du valde bort det.
- `plans/` är gitignorerad. Sidorna på Pi:n är arkivet, inte git.

## Vad den här skillen INTE gör

- Sparar inte recept (→ `recipe`).
- Ändrar inte befintliga recept (→ `edit-recipe`).
- Skriver inte till Notion (→ `shopping-list`, som är på väg att pensioneras).
- Handlar inte själv i webbläsaren (→ `grossist-order`).
- Sätter inte upp filservern på Pi:n (→ `docs/pi-setup.md`).
