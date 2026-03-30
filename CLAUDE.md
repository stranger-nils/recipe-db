# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Vision

A personal recipe website — a clean, user-friendly gallery of favorite recipes. The goal is a polished reading and browsing experience, not a cooking assistant. Recipes are created and modified through Claude Code directly, not through the website UI.

**Core principles:**
- Design and UX comes first — the interface should feel like a well-crafted recipe book, not a CRUD app
- Recipes evolve over time; version history and diff-style comparisons (similar to how code changes are tracked in git) are a first-class feature
- No AI chat, no shopping lists — these are out of scope

## Features

**In scope:**
- Recipe gallery with fast filtering by category, tags, ingredients, etc.
- Recipe detail view with instructions, ingredients, metadata, and images
- Version history per recipe — ability to browse past versions and compare changes (diff view, similar to git diff)
- Recipe editing via Claude Code (not through the website)

**Out of scope (do not add or restore):**
- Shopping list generation
- AI chat / chatbot interface
- User authentication (not planned)

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

**Production start:**
```bash
gunicorn app:app
```

**Import CSV data to SQLite:**
```bash
python scripts/turso_to_sqlite.py
```

## Architecture

Single-file Flask app (`app.py`) with Jinja2 templates and SQLAlchemy for database access.

**Database:**
- Local dev: SQLite (`dev.db`)
- Production: Turso (libsql-compatible SQLite via `sqlalchemy-libsql`)
- Connection chosen at startup based on `DATABASE_URL` env var
- Raw SQL via SQLAlchemy `text()` — no ORM models, just direct queries

**Tables:** `recipe`, `ingredient`, `recipe_ingredient` (many-to-many junction)
- Version history is not yet implemented — recipes do not currently store change history. This is a planned feature.

**Image storage:**
- Local dev: `static/uploads/`
- Production: Supabase (toggled by `USE_SUPABASE` flag derived from env vars)

**Frontend:** Inline CSS in Jinja2 templates, jQuery + Select2 for multi-select ingredient filters, vanilla JS elsewhere. No build step.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | `sqlite:///dev.db` for local; Turso URL for prod |
| `FLASK_SECRET_KEY` | Session encryption |
| `TURSO_DB_URL` | Production Turso database URL |
| `TURSO_DB_AUTH_TOKEN` | Production Turso auth token |
| `SUPABASE_URL` | Image storage (optional, enables cloud upload) |
| `SUPABASE_API_KEY` | Supabase credentials |
