#!/usr/bin/env bash
# sync-skills.sh
#
# Synkar projekt-skills (recipe-db/.claude/skills/) till den globala
# skill-mappen (~/.claude/skills/) så att Cowork upptäcker dem.
#
# Bakgrund: Cowork laddar bara skills från ~/.claude/skills/, inte från
# projektets .claude/skills/. Vi behåller projekt-versionerna som "source
# of truth" (versioneras i git) och synkar dem ut vid session-start.
#
# Script:et är idempotent och säkert att köra flera gånger.
# Det rör ALDRIG andra mappar i ~/.claude/skills/ som inte finns i detta
# projekt — andra projekt kan ha synkat sina egna skills dit.
#
# Anropas automatiskt av Claude Code vid session-bootstrap. Se
# .claude/CLAUDE_CODE_BOOTSTRAP.md.

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="$PROJECT_ROOT/.claude/skills"
TARGET_DIR="${HOME}/.claude/skills"

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "Inga skills att synka — $SOURCE_DIR finns inte."
  exit 0
fi

mkdir -p "$TARGET_DIR"

synced=0
for skill_dir in "$SOURCE_DIR"/*/; do
  [[ -d "$skill_dir" ]] || continue
  skill_name=$(basename "$skill_dir")
  target="$TARGET_DIR/$skill_name"

  # Mirror skill-innehållet. --delete tar bort filer i target som inte
  # finns i source (t.ex. om en hjälpfil är borttagen ur skill:en),
  # men påverkar bara filer INNE i den specifika skill-mappen.
  mkdir -p "$target"
  rsync -a --delete "$skill_dir" "$target/"
  echo "✓ Synced: $skill_name"
  synced=$((synced + 1))
done

echo ""
echo "Klart. $synced skill(s) synkade till $TARGET_DIR"
echo "Cowork plockar upp dem vid nästa session-start."
