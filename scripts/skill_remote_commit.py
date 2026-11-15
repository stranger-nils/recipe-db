#!/usr/bin/env python3
"""
Apply pending-commit JSON files (from the recipe skill) via the recipe HTTP API.

The recipe DB lives on the Raspberry Pi (nils-rpi) and is only written through
the API — never directly to SQLite. This script POSTs each commit to
$RECIPE_API_URL/api/recipe, which creates the recipe, links ingredients and
writes recipe_version v1 atomically.

Usage:
    python3 scripts/skill_remote_commit.py .claude/pending-commits/*.json
    python3 scripts/skill_remote_commit.py < some-commit.json     # stdin, no file move

Files that apply cleanly are moved to .claude/applied-commits/. Failed files
stay where they are. Prints one JSON line per commit:
    {"file": ..., "status": "ok"|"error", "recipe_id": N, "version_number": N, "message": ...}

Config is read from the environment, falling back to .claude/.env:
RECIPE_API_URL and RECIPE_API_TOKEN. The token is never printed.
"""
import json
import os
import shutil
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
ENV_FILE = REPO / ".claude" / ".env"
APPLIED_DIR = REPO / ".claude" / "applied-commits"

# Fields the API accepts for a new recipe. Commit metadata is dropped.
RECIPE_FIELDS = ("title", "description", "instructions", "notes", "tags",
                 "type", "kitchen", "ingredients")


def load_config():
    env = {}
    if ENV_FILE.exists():
        for line in ENV_FILE.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip())
    url = os.environ.get("RECIPE_API_URL") or env.get("RECIPE_API_URL")
    tok = os.environ.get("RECIPE_API_TOKEN") or env.get("RECIPE_API_TOKEN")
    if not url or not tok:
        sys.exit("RECIPE_API_URL / RECIPE_API_TOKEN saknas (env eller .claude/.env).")
    return url.rstrip("/"), tok


def post_recipe(url, tok, commit):
    op = commit.get("operation", "create")
    if op != "create":
        return {"status": "error",
                "message": f"operation '{op}' stöds inte — edits går via edit-recipe-skillen."}
    body = {k: commit[k] for k in RECIPE_FIELDS if k in commit}
    req = urllib.request.Request(
        url + "/api/recipe",
        data=json.dumps(body).encode(),
        method="POST",
        headers={"Authorization": "Bearer " + tok,
                 "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.load(resp)
        return {"status": "ok", "recipe_id": data.get("recipe_id"),
                "version_number": data.get("version_number"),
                "message": "skapat"}
    except urllib.error.HTTPError as e:
        try:
            detail = json.load(e)
        except Exception:
            detail = {"error": e.reason}
        msg = {401: "fel token (stämmer inte med Pi:ns recipe-db/.env)",
               503: "RECIPE_API_TOKEN inte satt på servern"}.get(e.code, detail)
        return {"status": "error", "http_status": e.code, "message": msg}
    except (urllib.error.URLError, TimeoutError) as e:
        return {"status": "error",
                "message": f"når inte {url} ({e}) — är Pi:n/Tailscale uppe?"}


def main():
    url, tok = load_config()
    files = sys.argv[1:]
    if not files:
        res = post_recipe(url, tok, json.load(sys.stdin))
        print(json.dumps({"file": "<stdin>", **res}, ensure_ascii=False))
        sys.exit(0 if res["status"] == "ok" else 1)

    failed = 0
    for f in files:
        path = Path(f)
        try:
            res = post_recipe(url, tok, json.loads(path.read_text()))
        except (OSError, json.JSONDecodeError) as e:
            res = {"status": "error", "message": f"kunde inte läsa: {e}"}
        if res["status"] == "ok":
            APPLIED_DIR.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), APPLIED_DIR / path.name)
        else:
            failed += 1
        print(json.dumps({"file": path.name, **res}, ensure_ascii=False))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
