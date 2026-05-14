#!/usr/bin/env python3
"""
SQLite backup helper. Two modes:

    python3 scripts/backup_db.py daily
        Snapshot tagged "daily". Prunes daily snapshots older than 14 days.

    python3 scripts/backup_db.py pre-edit [--note=<slug>]
        Snapshot tagged "pre-edit" (called by app.py before each user-initiated
        edit). Keeps the 50 most recent.

Reads DB path and backup directory from env:
    RECIPE_DB_PATH   absolute path to recipe.db (default: /app/recipe.db inside
                     the container, ./recipe.db otherwise)
    BACKUP_DIR       absolute path to backup directory. If unset, the script
                     exits 0 silently (so local dev is a no-op).

Backups are written to:
    $BACKUP_DIR/recipe-<tag>-<YYYYmmddTHHMMSSZ>[--<note>].db

Uses SQLite's online backup API — safe to run while the app is serving.
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

DAILY_KEEP_DAYS = 14
PRE_EDIT_KEEP_COUNT = 50


def _default_db_path() -> str:
    if Path("/app/recipe.db").exists():
        return "/app/recipe.db"
    return str(Path(__file__).resolve().parent.parent / "recipe.db")


def snapshot(db_path: str, backup_dir: Path, tag: str, note: str | None) -> Path:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    suffix = f"--{note}" if note else ""
    out = backup_dir / f"recipe-{tag}-{ts}{suffix}.db"
    backup_dir.mkdir(parents=True, exist_ok=True)
    src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        dst = sqlite3.connect(str(out))
        try:
            with dst:
                src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()
    return out


def prune_daily(backup_dir: Path, keep_days: int) -> int:
    cutoff = datetime.now(timezone.utc).timestamp() - keep_days * 86400
    removed = 0
    for f in backup_dir.glob("recipe-daily-*.db"):
        if f.stat().st_mtime < cutoff:
            f.unlink()
            removed += 1
    return removed


def prune_pre_edit(backup_dir: Path, keep_count: int) -> int:
    files = sorted(backup_dir.glob("recipe-pre-edit-*.db"), key=lambda p: p.stat().st_mtime)
    excess = files[:-keep_count] if len(files) > keep_count else []
    for f in excess:
        f.unlink()
    return len(excess)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("tag", choices=["daily", "pre-edit"])
    parser.add_argument("--note", default=None, help="optional slug appended to filename")
    args = parser.parse_args()

    backup_dir_env = os.environ.get("BACKUP_DIR")
    if not backup_dir_env:
        # No-op when not configured (local dev default).
        return 0
    backup_dir = Path(backup_dir_env)

    db_path = os.environ.get("RECIPE_DB_PATH") or _default_db_path()
    if not Path(db_path).exists():
        print(f"backup_db: source DB not found: {db_path}", file=sys.stderr)
        return 1

    out = snapshot(db_path, backup_dir, args.tag, args.note)
    if args.tag == "daily":
        pruned = prune_daily(backup_dir, DAILY_KEEP_DAYS)
    else:
        pruned = prune_pre_edit(backup_dir, PRE_EDIT_KEEP_COUNT)

    print(f"backup_db: wrote {out.name} (pruned {pruned})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
