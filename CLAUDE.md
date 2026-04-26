# CLAUDE.md

This file provides guidance to Claude (in any environment) when working with code in this repository.

## Vision

A personal recipe website — a clean, user-friendly gallery of favorite recipes. The goal is a polished reading and browsing experience alongside a workflow for developing and iterating on recipes over time.

**Core principles:**
- Design and UX comes first — the interface should feel like a well-crafted recipe book, not a CRUD app.
- Recipes evolve over time; version history and diff-style comparisons (similar to how code changes are tracked in git) are a first-class feature.
- Recipes can be authored/edited either via Claude in chat (recipe skill) or via the website's built-in edit UI. The database is the single source of truth.

## Features

**In scope:**
- Recipe gallery with fast filtering by category, tags, ingredients, etc.
- Recipe detail view with instructions, ingredients, metadata, and images.
- Recipe editing via the website UI (works from any device).
- Recipe creation/editing via Claude in chat (`recipe` skill).
- Version history per recipe — browse past versions and compare changes (diff view, similar to git diff).
- Shopping list generation within the website: pick N recipes, produce a consolidated list grouped by grocery category. No AI chat involvement — pure web UI.
- Shopping list generation via Claude in chat (`shopping-list` skill) — sources recipes from the Notion Recept-pipeline database, saves the result as a new entry in the Notion Inköpslistor database, categorized by store layout. Complementary to the planned in-website feature: the web UI is for "click and pick from recipe DB", the chat skill is for "I'll tell you what I'm cooking, you build the list".

**Out of scope:**
- AI chat / chatbot interface embedded in the website.
- User authentication (personal site, no multi-user support planned).
- Shopping list generation written into the SQLite recipe DB (it lives in Notion instead — see `shopping-list` skill).

## Working modes — where Claude runs

This project is worked on across two Claude environments with complementary roles:

**Cowork (desktop app, sandboxed)** handles:
- Recipe brainstorming and drafting *new* recipes (via the `recipe` skill).
- Editing/iterating on *existing* recipes (via the `edit-recipe` skill) — writes directly to the VPS database over the authenticated HTTP API. No Claude Code roundtrip needed.
- Notion Kanban management for the recipe pipeline.
- Shopping list generation (via the `shopping-list` skill) — saves to the Notion Inköpslistor database.
- File/code edits that don't require VPS shell access (e.g., Flask feature work, template changes, docs).
- For *new* recipes, the `recipe` skill still writes a pending-commit JSON file to `.claude/pending-commits/`, since new recipes are rarer and benefit from the manual review step in Claude Code (especially for new ingredients).

**Claude Code (terminal on the user's Macbook)** handles:
- Applying pending commits (new recipes) to the VPS database via SSH.
- Running migrations against the VPS database (e.g., version history schema changes).
- Skill synchronization (project `.claude/skills/` → user-global `~/.claude/skills/`) at session start, so Cowork picks them up. See `scripts/sync-skills.sh`.
- Any work that requires direct shell access to the VPS (`ssh minvps`) — server-side debugging, log inspection, container restarts.
- Note: edits to existing recipes can also be done via Claude Code, but the `edit-recipe` skill there uses the same HTTP API as Cowork — there's no longer a separate "direct SSH edit" path.

Both `recipe` and `edit-recipe` skills work in either environment.

See `docs/WORKFLOW_OVERHAUL_PLAN.md` for the detailed implementation plan, and `.claude/CLAUDE_CODE_BOOTSTRAP.md` for Claude Code session orientation.

## Skills

Custom skills for this project live in `.claude/skills/`. They are the source of truth and versioned in git.

| Skill | Purpose |
|---|---|
| `recipe` | Brainstorm and save *new* recipes. Cowork writes pending-commits; Claude Code applies them via SSH. Slash: `/recipe`. |
| `edit-recipe` | Iterate on an *existing* recipe via post-cook reflection. Reads/writes via the HTTP API (`RECIPE_API_TOKEN`). Logs a new version with a `change_note`. Slash: `/edit-recipe`. |
| `shopping-list` | Build a consolidated shopping list from recipes in the Notion Recept-pipeline; save as a categorized entry in the Notion Inköpslistor database. |

**Sync:** Cowork only discovers skills under `~/.claude/skills/`, not project-level. `scripts/sync-skills.sh` mirrors `.claude/skills/` → `~/.claude/skills/` and is run by Claude Code at session start. Always edit skills in this repo, never directly in the global folder — global edits get overwritten on next sync.

## Commands

**Run locally:**
```bash
python app.py
```
Starts Flask dev server on `http://localhost:5001`.

**Install dependencies:**
```bash
pip install -r requirements.txt
```

**Production start (via Docker on VPS):**
```bash
docker compose up --build -d
```

**Import CSV data to SQLite (one-off bootstrap):**
```bash
python scripts/csv_to_sqlite.py
```

## Architecture

Single-file Flask app (`app.py`) with Jinja2 templates and SQLAlchemy for database access.

**Database:** SQLite, used both locally and in production.
- Local dev: `recipe.db` in repo root (bind-mounted out of the Docker container when running locally via compose, or used directly by `python app.py`).
- Production (VPS): `/opt/recipe-db/data/recipe.db`, bind-mounted into the container at `/app/recipe.db`.
- Connection configured via the `DATABASE_URL` env var; defaults to `sqlite:///recipe.db`.
- Raw SQL via SQLAlchemy `text()` — no ORM models, just direct queries.

**Tables:** `recipe`, `ingredient`, `recipe_ingredient` (many-to-many junction). Version history (`recipe_version`) is a planned addition; see the workflow overhaul plan.

**Image storage:** Local filesystem in `static/uploads/` on both local dev and VPS. On VPS, bind-mounted from `/opt/recipe-db/data/uploads`.

**Frontend:** Inline CSS in Jinja2 templates, jQuery + Select2 for multi-select ingredient filters, vanilla JS elsewhere. No build step.

**Deployment:** VPS (Debian/Ubuntu), Docker + docker-compose + nginx reverse proxy. GitHub Actions (`.github/workflows/deploy.yml`) runs `git pull && docker compose up --build -d` on push to `master` via SSH.

## Recipe HTTP API

The Flask app exposes a small JSON API used by the `edit-recipe` skill to read recipes and commit new versions without going through SSH. All endpoints require `Authorization: Bearer $RECIPE_API_TOKEN`.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/recipe/search?q=<text>` | GET | Title substring search; returns `{results: [{id, title, section, menu}]}`. |
| `/api/recipe/<id>` | GET | Full recipe + ingredients + `current_version_number`. |
| `/api/recipe/<id>/commit-edit` | POST | Apply an edit. Body must include `change_note` and `expected_version_number`; remaining fields are partial — missing fields keep current values. Returns 409 on optimistic version conflict. |

Server-side logic lives in `apply_recipe_edit()` in `app.py`, which is the same function the web edit form uses. New version rows are tagged `changed_by='chat'` (skill) or `'web'` (form).

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | SQLite connection string; defaults to `sqlite:///recipe.db`. |
| `FLASK_SECRET_KEY` | Session encryption. |
| `RECIPE_API_TOKEN` | Bearer token for `/api/recipe/*`. Set on VPS in `/opt/recipe-db/.env`. If empty/unset the API returns 503. The Cowork-side token lives in `.claude/.env` (gitignored) — see `.claude/.env.example`. |
