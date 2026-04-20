# Claude Code Session — Bootstrap

Den här filen orienterar en Claude Code-session som precis har öppnats i `recipe-db`-repot på Nils Macbook.

## Var du är

Detta är Nils personliga receptdatabas. Du kör i `claude` (Claude Code) på hans Macbook. Du har direkt SSH-access till VPS:en via aliaset `ssh minvps` (som är `root@187.77.67.116`).

Systerverktyget är **Cowork** (desktop-appen) som kör i en sandbox utan nätverksaccess till VPS:en. Cowork hanterar recept-brainstorming och Notion Kanban. Du hanterar allt som kräver att faktiskt skriva till databasen.

## Start-checklista

1. Läs `CLAUDE.md` (rotmappen) — särskilt "Working modes"-sektionen.
2. Läs `docs/WORKFLOW_OVERHAUL_PLAN.md` — full plan för vad som ska göras.
3. Kolla efter pending commits: `ls -la .claude/pending-commits/`. Om det finns filer där behöver de applicera till VPS.
4. Verifiera SSH-access: `ssh minvps 'echo ok'`.

## Vad du gör — typiska uppgifter

**"apply pending" / "push"** — Applicera pending-commits från Cowork:

1. Läs alla filer i `.claude/pending-commits/` (JSON-format, se schema i `docs/WORKFLOW_OVERHAUL_PLAN.md`).
2. Visa batch-preview för användaren, bekräfta.
3. För varje commit: bygg INSERT/UPDATE-SQL, kör via SSH på VPS:ens SQLite-fil (`/opt/recipe-db/data/recipe.db`), logga en rad i `recipe_version`.
4. Vid success: flytta filen till `.claude/applied-commits/`.
5. Vid error: rapportera, låt filen ligga kvar i pending.

**Edita befintligt recept** — Användaren säger "ändra recept X":

1. Läs aktuellt recept från VPS: `ssh minvps "sqlite3 /opt/recipe-db/data/recipe.db 'SELECT * FROM recipe WHERE id=<X>'"`.
2. Föreslå ändringar i chatten, visa diff-preview.
3. Vid bekräftelse: kör UPDATE via SSH, logga ny `recipe_version`-rad.

**Skapa recept direkt i Claude Code** — Användaren brainstormar direkt här istället för i Cowork:

1. Följ `recipe`-skillens standardflöde (brainstorm → preview → push).
2. På push: kör direkt mot VPS (inte pending-commit). Logga version.

**Köra migrationer** — t.ex. `scripts/migrations/001_recipe_version.py`:

1. Testa lokalt först mot `recipe.db` om möjligt.
2. Kör mot VPS: `scp scripts/migrations/001_recipe_version.py minvps:/tmp/ && ssh minvps 'python3 /tmp/001_recipe_version.py /opt/recipe-db/data/recipe.db'`.

## Aktuellt läge (uppdateras allteftersom)

**Fas 1 (cleanup)**: Klar. Utförd i Cowork på branchen `claude-workflow-overhaul`.

**Fas 2 (versionshistorik)**: Ej påbörjad. **Ditt nästa jobb är troligen detta.** Se plan för schema och migration.

**Fas 3 (skill ↔ VPS helper)**: Ej påbörjad. Efter fas 2.

**Fas 4 (diff-UI)**: Ej påbörjad.

**Fas 5 (inköpslistor i Flask)**: Ej påbörjad.

**Fas 6 (Notion Kanban)**: Sköts i Cowork.

## Viktiga paths

- Lokal repo: (där du står nu)
- Lokal DB-fil (kan vara stale/tom): `recipe.db` i repo-roten.
- VPS DB-fil (auktoritativ): `/opt/recipe-db/data/recipe.db`.
- VPS app-dir: `/opt/recipe-db/`.
- Pending commits från Cowork: `.claude/pending-commits/`.

## Säkerhetsregler

- Rör aldrig master utan bekräftelse.
- Kör aldrig `git push --force`.
- Testa alla SQL-transaktioner i en `BEGIN; ... ROLLBACK;`-runda innan `COMMIT` om du är osäker.
- Gör ALLTID en backup av VPS-DB:n innan migrationer: `ssh minvps 'cp /opt/recipe-db/data/recipe.db /opt/recipe-db/data/recipe.db.bak-$(date +%Y%m%d-%H%M%S)'`.
