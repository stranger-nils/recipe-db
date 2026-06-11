# mise — a recipe IDE

> A personal recipe book that behaves like a code editor.
> Recipes open as tabs, ingredients live in a catalog, and every edit is a new version you can diff against the last one.

This is my own cookbook, on my own terms. It started as a CRUD app for storing favorite dishes and slowly turned into something more interesting: a writing environment for recipes — quiet, monospaced, version-tracked, and built to grow with how I actually cook.

The name comes from *mise en place*. The aesthetic comes from a JetBrains window at 1 AM.

---

## What it is

A single-file Flask app with a Jinja + vanilla-JS frontend. No build step. No accounts. No chatbot pasted into the corner. Just a careful reading and editing experience around a SQLite database that I trust completely because I can see it on disk.

**Three views, switched from a left rail:**

- **Recipes** — recipes open as tabs (like files in an editor), with a file-tree sidebar, an inline editor, and a diff view that compares any two versions of the same dish side by side.
- **Ingredients** — a catalog of every ingredient I've ever used. The source of truth that recipes reference.
- **Planning** — pick a few recipes, get a consolidated shopping list grouped by store section.

**Versioned by default.** Every save writes a new row to `recipe_version`. Tweaked the salt next time you made the pasta? It's a new version with a `change_note`, and the previous one is still there — `v3` vs `v4`, side by side, like a git diff.

**Edited from anywhere.** The web UI works on phone and desktop. A small authenticated HTTP API (`/api/recipe/*`) lets me edit recipes from a chat with Claude after I've cooked something and want to write down what I'd change — the `edit-recipe` skill posts a new version with a note, and the diff shows up the next time I open the recipe.

---

## Why

Recipe sites optimize for SEO. Recipe apps optimize for sign-ups. Notebooks lose the recipe you made last March. I wanted one place that:

- Reads like a cookbook, not a CRUD form.
- Remembers that the recipe *changed* — and what the previous version looked like.
- Lets me capture the small fix the moment I think of it ("less salt, longer in the oven"), without losing the original.
- Stays mine. SQLite on a VPS I control, a bind-mounted folder, a `cp` away from a backup.

It's a love letter to the way recipes actually evolve — not as fixed artifacts, but as drafts you keep revisiting.

---

## Stack

| | |
|---|---|
| Backend | Flask + SQLAlchemy (raw SQL via `text()`, no ORM models) |
| Database | SQLite — `recipe`, `ingredient`, `recipe_ingredient`, `recipe_version` |
| Frontend | Jinja2 templates, vanilla JS, a single monospace family (IBM Plex Mono) |
| Deploy | Docker + docker-compose + nginx on a small VPS, auto-deployed from `master` via GitHub Actions |
| Images | Filesystem under `static/uploads/`, bind-mounted on the VPS |
| Authoring | Web edit form, or the `recipe` / `edit-recipe` Claude skills via the HTTP API |

No bundler. No Node. No framework on the frontend. The whole thing is intentionally small enough to read in an afternoon.

---

## Run it locally

```bash
pip install -r requirements.txt
python app.py
```

Then open <http://localhost:5001>.

To deploy a copy on your own VPS, see `docker-compose.yml` and `.github/workflows/deploy.yml` — both are short and assume nothing exotic.

---

## Project layout

```
app.py                      # the whole backend, ~1000 lines
templates/                  # Jinja templates (ide.html is the main view)
static/                     # mise.css, mise.js, uploads/
scripts/                    # one-off importers and maintenance
docs/                       # design notes and the workflow plan
.claude/skills/             # recipe, edit-recipe, shopping-list — custom Claude skills
```

The HTTP API lives in `app.py` under `/api/recipe/*` and is documented in [`CLAUDE.md`](CLAUDE.md), along with the working-modes split (Cowork for authoring, Claude Code for VPS shell work).

---

## Roadmap

Things I want to build, roughly in order of how much I miss them:

- [ ] Annotations on individual ingredients and steps (notes that travel with the recipe across versions).
- [ ] Richer diffs — a clearer "what changed in the method" view, not just textual.
- [ ] In-app shopping list builder with ingredient consolidation across recipes.
- [ ] Photo gallery view, with the photos I actually took.
- [ ] Public read-only mode for sharing a single recipe by link.

Things I deliberately don't want:

- A chatbot bolted into the UI.
- User accounts.
- A general-purpose recipe database (this is *my* cookbook).

---

## License

Personal project, no license declared. Read the code, take ideas, but please don't host a copy as a service.
