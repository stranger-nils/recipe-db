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
- Recipe creation/editing via Claude in chat (recipe skill).
- Version history per recipe — browse past versions and compare changes (diff view, similar to git diff).
- Shopping list generation within the website: pick N recipes, produce a consolidated list grouped by grocery category. No AI chat involvement — pure web UI.

**Out of scope:**
- AI chat / chatbot interface embedded in the website.
- User authentication (personal site, no multi-user support planned).
- Shopping list generation via the recipe skill / chat (the skill only handles recipe creation/editing).

## Working modes — where Claude runs

This project is worked on across two Claude environments with complementary roles:

**Cowork (desktop app, sandboxed)** handles:
- Recipe brainstorming and drafting (via the `recipe` skill).
- Notion Kanban management for the recipe pipeline.
- File/code edits that don't require VPS network access (e.g., Flask feature work, template changes, docs).
- When the user commits a recipe, the skill writes a pending-commit JSON file to `.claude/pending-commits/`. It does NOT write to the database directly — Cowork's sandbox has no network access to the VPS.

**Claude Code (terminal on the user's Macbook)** handles:
- Applying pending commits to the VPS database via SSH.
- Editing existing recipes on the VPS database.
- Running migrations against the VPS database (e.g., version history).
- Any work that requires direct access to the VPS (`ssh minvps`).

The same `recipe` skill works in both environments but detects which mode it is running in.

See `docs/WORKFLOW_OVERHAUL_PLAN.md` for the detailed implementation plan, and `.claude/CLAUDE_CODE_BOOTSTRAP.md` for Claude Code session orientation.

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

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | SQLite connection string; defaults to `sqlite:///recipe.db`. |
| `FLASK_SECRET_KEY` | Session encryption. |
