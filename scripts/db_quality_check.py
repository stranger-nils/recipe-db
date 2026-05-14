#!/usr/bin/env python3
"""
Data quality assertions ovanpå DB-schemat.

Schemat hindrar redan trasig data från att skrivas (FK, NOT NULL, UNIQUE,
CHECK). Detta script kompletterar med regler SQL-DDL inte kan uttrycka:
filsystem-existens, kontinuitet i sequences, semantiska heuristiker.

Usage:
    python3 scripts/db_quality_check.py [path/to/recipe.db] \\
        [--uploads-dir=path/to/static/uploads]

Exit codes:
    0  all expectations passed
    1  one or more expectations failed (details printed to stderr)
    2  could not run (missing DB, etc.)
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from dataclasses import dataclass
from pathlib import Path

# Image URLs to consider valid (in addition to disk existence and http(s)).
EMPTY_OR_NULL = ("", None)


@dataclass
class Expectation:
    name: str
    failed_rows: list  # list of (id, description) tuples; empty = pass


def expect_no_blank_recipe_titles(conn: sqlite3.Connection) -> Expectation:
    rows = conn.execute(
        "SELECT id, title FROM recipe WHERE title IS NULL OR TRIM(title) = ''"
    ).fetchall()
    return Expectation(
        "no_blank_recipe_titles",
        [(r[0], f"title={r[1]!r}") for r in rows],
    )


def expect_no_orphan_recipe_ingredient(conn: sqlite3.Connection) -> Expectation:
    rows = conn.execute("""
        SELECT ri.id, ri.recipe_id, ri.ingredient_id
        FROM recipe_ingredient ri
        LEFT JOIN recipe r ON r.id = ri.recipe_id
        LEFT JOIN ingredient i ON i.id = ri.ingredient_id
        WHERE r.id IS NULL OR i.id IS NULL
    """).fetchall()
    return Expectation(
        "no_orphan_recipe_ingredient",
        [(r[0], f"recipe_id={r[1]} ingredient_id={r[2]}") for r in rows],
    )


def expect_every_recipe_has_ingredients(conn: sqlite3.Connection) -> Expectation:
    rows = conn.execute("""
        SELECT r.id, r.title
        FROM recipe r
        LEFT JOIN recipe_ingredient ri ON ri.recipe_id = r.id
        WHERE ri.id IS NULL
    """).fetchall()
    return Expectation(
        "every_recipe_has_at_least_one_ingredient",
        [(r[0], f"title={r[1]!r}") for r in rows],
    )


def expect_image_urls_resolve(conn: sqlite3.Connection,
                              uploads_dir: Path) -> Expectation:
    rows = conn.execute(
        "SELECT id, title, image_url FROM recipe "
        "WHERE image_url IS NOT NULL AND TRIM(image_url) != ''"
    ).fetchall()
    failed = []
    for rid, title, url in rows:
        if url.startswith(("http://", "https://")):
            continue  # external URL — we don't HEAD-check (offline-friendly)
        if url.startswith("/static/uploads/"):
            filename = url[len("/static/uploads/"):]
            if not (uploads_dir / filename).exists():
                failed.append((rid, f"missing file: {url} (recipe {title!r})"))
            continue
        failed.append((rid, f"unrecognised image_url shape: {url!r}"))
    return Expectation("image_urls_resolve_to_files_or_http", failed)


def expect_version_numbers_contiguous(conn: sqlite3.Connection) -> Expectation:
    """For each recipe with versions, version_numbers should be 1..N contiguous."""
    bad = []
    rows = conn.execute("""
        SELECT recipe_id, GROUP_CONCAT(version_number, ',') AS versions, COUNT(*) AS n
        FROM recipe_version GROUP BY recipe_id
    """).fetchall()
    for rid, versions_csv, n in rows:
        versions = sorted(int(v) for v in versions_csv.split(","))
        expected = list(range(1, n + 1))
        if versions != expected:
            bad.append((rid, f"versions={versions} (expected 1..{n})"))
    return Expectation("recipe_version_numbers_contiguous_per_recipe", bad)


def expect_kitchen_staple_is_bool(conn: sqlite3.Connection) -> Expectation:
    rows = conn.execute(
        "SELECT id, name, kitchen_staple FROM ingredient "
        "WHERE kitchen_staple NOT IN (0, 1)"
    ).fetchall()
    return Expectation(
        "kitchen_staple_is_zero_or_one",
        [(r[0], f"name={r[1]!r} value={r[2]!r}") for r in rows],
    )


def expect_unique_ingredient_names(conn: sqlite3.Connection) -> Expectation:
    """The UNIQUE COLLATE NOCASE index should already prevent this, but
    check anyway so the QC report is self-contained."""
    rows = conn.execute("""
        SELECT LOWER(name), COUNT(*) FROM ingredient
        GROUP BY LOWER(name) HAVING COUNT(*) > 1
    """).fetchall()
    return Expectation(
        "ingredient_names_unique_case_insensitive",
        [(None, f"name={r[0]!r} appears {r[1]}x") for r in rows],
    )


ALL_EXPECTATIONS = [
    expect_no_blank_recipe_titles,
    expect_no_orphan_recipe_ingredient,
    expect_every_recipe_has_ingredients,
    expect_version_numbers_contiguous,
    expect_kitchen_staple_is_bool,
    expect_unique_ingredient_names,
    # image_urls_resolve handled separately because it needs uploads_dir.
]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("db", nargs="?", default="data/recipe.db")
    parser.add_argument(
        "--uploads-dir",
        default=None,
        help="path to static/uploads dir for image_url existence check. "
             "Skipped if omitted.",
    )
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"✗ DB not found: {db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    conn.execute("PRAGMA foreign_keys = ON")

    results = [check(conn) for check in ALL_EXPECTATIONS]
    if args.uploads_dir:
        results.append(
            expect_image_urls_resolve(conn, Path(args.uploads_dir))
        )

    print(f"=== Data quality report for {db_path} ===\n")
    passed = 0
    failed = 0
    for r in results:
        if r.failed_rows:
            failed += 1
            print(f"✗ {r.name}: {len(r.failed_rows)} failing row(s)")
            for ident, desc in r.failed_rows[:10]:
                print(f"    id={ident}  {desc}")
            if len(r.failed_rows) > 10:
                print(f"    ... and {len(r.failed_rows) - 10} more")
        else:
            passed += 1
            print(f"✓ {r.name}")

    print(f"\n{passed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
