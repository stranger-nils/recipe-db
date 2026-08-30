# Veckoflödet — från tom vecka till lagad mat

Hur de fyra skillsen hänger ihop i praktiken. Läs `CLAUDE.md` för arkitekturen;
det här är bruksanvisningen.

```
  /veckomeny  ──▶  förslag i chatten  ──▶  "kör"  ──▶  plans/<slug>.json
                        ▲                                    │
                        └──── justera ◀───┘                  ▼
                                                   build_plan_page.py
                                                             │
                                                             ▼
                                                    publish-plan.sh
                                                             │
                                                             ▼
                                            https://nils-rpi:8443/<slug>.html
                                                             │
                                        ┌────────────────────┴─────────────┐
                                        ▼                                  ▼
                                 /grossist-order                     du lagar maten
                                  Mathem-varukorg                          │
                                        │                                  ▼
                                  du beställer                    "spara nr 3" → /recipe
                                                                           │
                                                                           ▼
                                                            efter tillagning → /edit-recipe
```

## Söndag (eller när veckan ska planeras)

**1. Starta planeringen**

> `/veckomeny` — eller bara "planera veckan", "fem middagar till veckan"

Claude frågar tre saker om de inte framgår: **antal rätter**, **önskemål**
(snabbt, säsong, vegetariskt, vad du har hemma) och **källa** — befintliga
recept ur databasen, helt nya, eller en blandning.

> ⚠️ Säger du "mix" tolkas det som *variation* i veckan, inte som källa.
> Vill du blanda databas och nytt, säg det rakt ut.

**2. Justera förslagen**

Du får fem korta förslag — två-tre rader var. Inga fullständiga recept än, det
är hela poängen: det ska vara billigt att säga "byt ut trean" eller "ingen ört
får återkomma i två rätter". Iterera så många varv du vill.

**3. Godkänn**

> "kör"

Först nu skrivs recepten ut, `plans/<slug>.json` byggs och sidan renderas.

**4. Publicera**

```bash
cd ~/recipe-db && ./scripts/publish-plan.sh
```

Har du installerat vakten i `docs/autopublish.md` sker det av sig självt inom
~15 sekunder. Sidan hamnar på `https://nils-rpi:8443/<slug>.html`.

## I butiken eller framför datorn

**5. Handla**

> `/grossist-order` — eller "handla listan"

Claude öppnar Mathem i den inbyggda webbläsaren (logga in där en gång; profilen
är beständig), matchar varje vara mot rätt artikel och förpackningsstorlek, och
fyller varukorgen. Den stannar där — **du väljer leveranstid och betalar själv.**

Andra körningen och framåt går det mycket fortare: `mathem-mapping.json` minns
vilken artikel som är rätt för varje ingrediens.

Vill du hellre handla i butik: öppna veckomeny-sidan i mobilen, gå till fliken
*Inköpslista* och bocka av. Avbockningen sparas i telefonen. Bockar du ur en
rätt räknas listan om direkt.

## Under veckan

**6. Laga**

Sidan har hela recept under *Recept* på varje rätt. Öppna den i mobilen eller på
en padda i köket.

**7. Spara det som var bra**

> "spara nr 3" / "den där pastan vill jag ha kvar"

`veckomeny` lämnar över till `recipe`-skillen, som kanoniserar ingredienserna mot
prod, visar en commit-preview och skriver till databasen på "push". Utkast på
veckomeny-sidan hamnar **aldrig** i databasen av sig själva.

**8. Efterkok**

> `/edit-recipe` — eller "jag lagade X igår"

Reflektera över vad som kan bli bättre, få en ny version med `change_note` i
versionshistoriken.

## Vad som ska vara sant för att allt ska funka

| Sak | Kontroll |
|---|---|
| Pi:n serverar | `curl -s -o /dev/null -w '%{http_code}\n' https://nils-rpi:8443/` → `200` |
| Skills i Claude Code | `./scripts/sync-skills.sh` vid sessionsstart |
| Skills i Cowork | Manuell uppladdning under Customize → Skills efter varje ändring |
| API:t når VPS:en | `RECIPE_API_URL` + `RECIPE_API_TOKEN` i `.claude/.env` |
| Upprepningsfiltret | `/api/cook-log` måste vara deployad; annars körs veckan utan det |

**Skill-versionerna glider isär tyst.** Repot är source of truth, men Cowork
laddar kontokopian. Varje SKILL.md har en `SKILL_VERSION`-stämpel och jämför sig
mot repot vid start — men bara om `recipe-db` är ansluten som mapp i sessionen.
Anslut den alltid.

## Vad varje skill äger

| Skill | Äger | Rör aldrig |
|---|---|---|
| `veckomeny` | veckoplanering, sidan, inköpslistan | receptdatabasen, Notion |
| `recipe` | nya recept in i databasen | befintliga recept |
| `edit-recipe` | nya versioner av befintliga recept | nya recept |
| `grossist-order` | Mathem-varukorgen | kassan, inloggning, betalning |

## Städning

`plans/` är gitignorerad och växer med en JSON + en HTML per vecka. Pi:n är
arkivet. Vill du rensa: `rm ~/recipe-db/plans/<slug>.*` och kör
`publish-plan.sh --prune`.
