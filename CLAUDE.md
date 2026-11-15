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
- Shopping list generation via Claude in chat (`shopping-list` skill) — sources recipes from the Notion Recept-pipeline database, saves the result as a new entry in the Notion Inköpslistor database, categorized by store layout.
- Grocery ordering via the browser (`grossist-order` skill) — takes a shopping list and fills a Mathem cart using the in-app browser. Learns an ingredient→product mapping over time (`references/mathem-mapping.json`). Never logs in, never completes a purchase.

**Out of scope:**
- AI chat / chatbot interface embedded in the website.
- User authentication (personal site, no multi-user support planned).
- Shopping list generation written into the SQLite recipe DB. Lists live in Notion (`shopping-list` skill) or are generated on the fly by the website's `/plan` tab.
- Weekly meal planning. The former `veckomeny` skill, plan renderer and publishing scripts were removed in 2026-11; Nils plans his own menus.

## Working modes — where Claude runs

This project is worked on across two Claude environments with complementary roles:

**Cowork (desktop app, sandboxed)** handles:
- Recipe brainstorming and drafting *new* recipes (via the `recipe` skill).
- Editing/iterating on *existing* recipes (via the `edit-recipe` skill) — writes to the recipe DB on the Pi over the authenticated HTTP API. No Claude Code roundtrip needed. (Unverified since the move: the API is tailnet-only, so if Cowork can't reach it, use Claude Code.)
- Notion Kanban management for the recipe pipeline.
- Shopping list generation (via the `shopping-list` skill) — saves to the Notion Inköpslistor database.
- File/code edits (e.g., Flask feature work, template changes, docs).
- Creating *new* recipes (via the `recipe` skill) — writes over the HTTP API (`POST /api/recipe`), same as edits. The pending-commit path (a JSON file in `.claude/pending-commits/`, applied later through the same API with `scripts/skill_remote_commit.py`) is the fallback when the API isn't configured/reachable.

**Claude Code (terminal on the user's Macbook)** handles:
- Creating and editing recipes via the `recipe` / `edit-recipe` skills over the HTTP API (the Mac is on the tailnet).
- Applying pending commits via the API (`scripts/skill_remote_commit.py`).
- Skill synchronization (project `.claude/skills/` → user-global `~/.claude/skills/`) at session start, so Cowork picks them up. See `scripts/sync-skills.sh`.

Both `recipe` and `edit-recipe` skills work in either environment.

See `docs/WORKFLOW_OVERHAUL_PLAN.md` for the detailed implementation plan, and `.claude/CLAUDE_CODE_BOOTSTRAP.md` for Claude Code session orientation.

## Skills

Custom skills for this project live in `.claude/skills/`. They are the source of truth and versioned in git.

| Skill | Purpose |
|---|---|
| `recipe` | Brainstorm and save *new* recipes. Writes only via the HTTP API (`POST /api/recipe`); pending-commits are the fallback when the API is unreachable. Follows the house rules shared with Iris (4 portions, numbered steps with temp/time, pro tips + alternatives in `notes`, `type` enum). Slash: `/recipe`. |
| `edit-recipe` | Iterate on an *existing* recipe via post-cook reflection. Reads/writes via the HTTP API (`RECIPE_API_TOKEN`). Logs a new version with a `change_note`. Slash: `/edit-recipe`. |
| `shopping-list` | Build a consolidated shopping list from recipes in the Notion Recept-pipeline; save as a categorized entry in the Notion Inköpslistor database. |
| `grossist-order` | Fill a Mathem cart from a shopping list. Reads search results as text, adds via each product article's own button, and remembers the chosen product URL per ingredient. Stops at a filled cart — Nils checks out himself. Slash: `/grossist-order`. |

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

**Production:** runs on the Pi, deployed via `iris-workspace` (see Deployment below).

**Import CSV data to SQLite (one-off bootstrap):**
```bash
python scripts/csv_to_sqlite.py
```

## Architecture

Single-file Flask app (`app.py`) with Jinja2 templates and SQLAlchemy for database access.

**Database:** SQLite.
- Production: on the Raspberry Pi `nils-rpi`, at `/home/nilslunden/docker/openclaw/data/workspace/recipe-db/data/recipe.db` (inside the OpenClaw container: `/root/.openclaw/workspace/recipe-db/data/recipe.db`). Shared with the OpenClaw agent Iris. **Only reached via the HTTP API** — no SSH, never write to the file directly.
- Local dev: `recipe.db` in repo root (an old copy from the VPS era; not a source of truth).
- Connection configured via the `DATABASE_URL` env var; defaults to `sqlite:///recipe.db`.
- Raw SQL via SQLAlchemy `text()` — no ORM models, just direct queries.
- Retired: the VPS (`minvps`, `/opt/recipe-db`, `https://recipedb.cloud`). Its DB is frozen at recipe id 41.

**Tables:** `recipe`, `ingredient`, `recipe_ingredient` (many-to-many junction). Version history (`recipe_version`) is a planned addition; see the workflow overhaul plan.

**Image storage:** Local filesystem in `static/uploads/`, bind-mounted from the data dir on the Pi.

**Frontend:** Inline CSS in Jinja2 templates, jQuery + Select2 for multi-select ingredient filters, vanilla JS elsewhere. No build step.

**Deployment:** The app runs in a container on the Pi (`nils-rpi`), API at `http://100.127.88.96:5001` (Tailscale) / `http://192.168.1.82:5001` (LAN). Since 2026-11-10 code changes go branch → PR in `stranger-nils/iris-workspace` → Nils reviews → merge → Iris deploys automatically (docker build/run + healthcheck; on the host: `scripts/pi-deploy.sh` with `docker-compose.rpi.yml`). New recipes need no deploy. Pushing to `master` in this repo deploys nothing; the old VPS workflow (`.github/workflows/deploy.yml`) is manual-only legacy.

## Recipe HTTP API

The Flask app exposes a small JSON API used by the `recipe` and `edit-recipe` skills to read recipes, create new ones, and commit new versions without going through SSH. All endpoints require `Authorization: Bearer $RECIPE_API_TOKEN`.

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/recipe/search?q=<text>` | GET | Title substring search; returns `{results: [{id, title, kitchen, type}]}`. Empty `q` = all recipes. |
| `/api/recipe/<id>` | GET | Full recipe + ingredients + `current_version_number`. |
| `/api/recipe` | POST | Create a new recipe. Body: `title` (required) + optional `description`, `instructions`, `notes`, `tags`, `type`, `kitchen`, `ingredients`. New ingredients need `grocery_category` + `default_unit` (else 400 with `missing_fields`). Creates the recipe, links ingredients, and writes `recipe_version` v1 atomically. Returns 201. |
| `/api/cook-log?since=<YYYY-MM-DD>` | GET | What has been cooked and when — `{results: [{recipe_id, title, version_number, cooked_at, rating}]}`, newest first. |
| `/api/recipe/<id>/commit-edit` | POST | Apply an edit. Body must include `change_note` and `expected_version_number`; remaining fields are partial — missing fields keep current values. Returns 409 on optimistic version conflict. |

Server-side logic lives in `apply_recipe_edit()` (edits) and `create_recipe()` (new recipes) in `app.py`, the same functions the web edit/new forms build on. New version rows are tagged `changed_by='chat'` (skill) or `'web'` (form).

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | SQLite connection string; defaults to `sqlite:///recipe.db`. |
| `FLASK_SECRET_KEY` | Session encryption. |
| `RECIPE_API_TOKEN` | Bearer token for `/api/recipe/*`. Set on the Pi in `recipe-db/.env`. If empty/unset the API returns 503. The client-side copy lives in `.claude/.env` (gitignored, never print it) — see `.claude/.env.example`. |
| `RECIPE_API_URL` | Client-side only (`.claude/.env`): `http://100.127.88.96:5001` (Pi over Tailscale). |
