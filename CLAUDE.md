# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

**Image storage:**
- Local dev: `static/uploads/`
- Production: Supabase (toggled by `USE_SUPABASE` flag derived from env vars)

**AI chat:** OpenAI client at `/chat` — stateful conversation stored in Flask session as `chat_history`. The assistant is named "René".

**Shopping list:** Session-stored dict of `{recipe_id: quantity}`, aggregated into a combined ingredient list at `/shopping_list`.

**Frontend:** Inline CSS in Jinja2 templates, jQuery + Select2 for multi-select ingredient filters, vanilla JS elsewhere. No build step.

## Environment Variables

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | `sqlite:///dev.db` for local; Turso URL for prod |
| `FLASK_SECRET_KEY` | Session encryption |
| `OPENAI_API_KEY` | GPT chat (René) |
| `TURSO_DB_URL` | Production Turso database URL |
| `TURSO_DB_AUTH_TOKEN` | Production Turso auth token |
| `SUPABASE_URL` | Image storage (optional, enables cloud upload) |
| `SUPABASE_API_KEY` | Supabase credentials |
