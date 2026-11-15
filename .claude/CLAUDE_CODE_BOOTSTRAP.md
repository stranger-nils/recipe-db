# Claude Code Session — Bootstrap

Den här filen orienterar en Claude Code-session som precis har öppnats i `recipe-db`-repot på Nils Macbook.

## Var du är

Detta är Nils personliga receptdatabas. Du kör i `claude` (Claude Code) på hans Macbook. Systerverktyget är **Cowork** (desktop-appen).

**Databasen ligger på Raspberry Pi:n `nils-rpi`** (sedan 2026-11). Flask-appen körs där i en container och delar databas med OpenClaw-agenten **Iris**.

- API: `http://100.127.88.96:5001` (Tailscale), `http://192.168.1.82:5001` (LAN). Satt som `RECIPE_API_URL` i `.claude/.env`.
- DB-fil på Pi:n: `/home/nilslunden/docker/openclaw/data/workspace/recipe-db/data/recipe.db` — rör den aldrig direkt.
- **Ingen SSH till Pi:n** — och det behövs inte. Läsning och skrivning av recept går bara via HTTP-API:t.
- Den gamla VPS:en (`minvps`, `/opt/recipe-db`, `https://recipedb.cloud`) är **ur bruk**. Dess databas är frusen vid recept-id 41. Använd den inte.

## Start-checklista

1. **Synka skills till global mapp** för Claude Code: `bash scripts/sync-skills.sh`. Detta uppdaterar INTE Cowork — se "Skill-synkning" nedan.
2. Läs `CLAUDE.md` (rotmappen) — särskilt "Working modes"-sektionen.
3. Kolla efter pending commits: `ls -la .claude/pending-commits/`. Finns det filer: applicera dem via API:t (se nedan).
4. Verifiera API:t (skriv aldrig ut tokenen):
   ```bash
   set -a; source .claude/.env; set +a
   curl -sS -o /dev/null -w '%{http_code}\n' -H "Authorization: Bearer $RECIPE_API_TOKEN" "$RECIPE_API_URL/api/recipe/search?q="
   ```
   200 = OK, 401 = fel token (be Nils om den från `recipe-db/.env` på Pi:n), timeout = Pi:n/Tailscale nere.

## Skill-synkning

Projektets skills bor i `.claude/skills/` (versioneras i git, source of truth).

> ⚠️ **Rättelse (2026-08-21).** Här stod tidigare att "Cowork laddar bara skills från `~/.claude/skills/`". Det är fel, och felet kostade två månaders tyst drift: Cowork-sessioner kör i Anthropics moln och kan inte se den här datorns hemkatalog alls. Cowork hämtar sin skill-lista från **Claude-kontot** vid sessionsstart.

En skill-ändring måste därför spridas åt **två håll**:

| Mål | Hur | Effekt |
|---|---|---|
| Claude Code | `bash scripts/sync-skills.sh` | direkt |
| Cowork | manuell uppladdning under **Customize → Skills** i Claude-appen | nästa Cowork-session |

`scripts/sync-skills.sh` sköter bara det första ledet. Det är idempotent och rör inte skills i den globala mappen som tillhör andra projekt.

**Driftvakt:** varje `SKILL.md` inleds med en `SKILL_VERSION`-stämpel och en instruktion som säger åt sessionen att jämföra sin egen version mot repo-kopian och säga till vid glapp. Ta inte bort den — det är den som gör drift synlig. Höj datumet när du ändrar en skill.

**Regel:** Redigera skills enbart under `.claude/skills/` (denna repo), aldrig direkt i `~/.claude/skills/`. Ändringar i den globala mappen försvinner nästa gång synken körs.

Om du lägger till en ny skill: skapa under `.claude/skills/<namn>/SKILL.md`, kör synken, och commita projekt-versionen.

## Vad du gör — typiska uppgifter

**Skapa recept** — följ `recipe`-skillen (brainstorm → preview → "push" → `POST /api/recipe`).

**Edita befintligt recept** — följ `edit-recipe`-skillen (`GET /api/recipe/<id>` → diff-preview → `POST /api/recipe/<id>/commit-edit`).

**"apply pending"** — pending-commits från en session som inte nådde API:t:

1. Visa batch-preview av filerna i `.claude/pending-commits/`, bekräfta.
2. `python3 scripts/skill_remote_commit.py .claude/pending-commits/*.json` — POSTar varje fil till API:t och flyttar lyckade till `.claude/applied-commits/`.

**Kodändringar i Flask-appen** — appen på Pi:n deployas från repot `stranger-nils/iris-workspace`, inte härifrån: branch → PR → Nils reviewar → merge → Iris deployar automatiskt (docker build/run + healthcheck; från värden finns `scripts/pi-deploy.sh` med `docker-compose.rpi.yml`). En push till `master` här deployar ingenting.

**Migrationer** — körs på Pi:n via deploy-flödet ovan (i `iris-workspace`), inte via SSH härifrån.

**Publicera veckomeny** — `scripts/publish-plan.sh` (separat file server på Pi:n, se `docs/pi-setup.md`).

## Viktiga paths

- Lokal repo: (där du står nu)
- Lokal `recipe.db` i repo-roten: gammal kopia från VPS-tiden, bara för lokal utveckling. Aldrig källa för riktiga data.
- Prod-DB: på Pi:n, nås bara via API:t.
- Pending commits: `.claude/pending-commits/`.

## Säkerhetsregler

- Rör aldrig master utan bekräftelse.
- Kör aldrig `git push --force`.
- Skriv aldrig direkt till SQLite — allt går via API:t.
- Skriv aldrig ut `RECIPE_API_TOKEN`.
