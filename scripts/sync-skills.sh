#!/usr/bin/env bash
# sync-skills.sh
#
# Synkar projekt-skills (recipe-db/.claude/skills/) till den globala
# skill-mappen (~/.claude/skills/) för CLAUDE CODE.
#
# ⚠️ VIKTIGT — detta script påverkar INTE Cowork.
#
# Tidigare stod här att "Cowork laddar bara skills från ~/.claude/skills/".
# Det är fel. Cowork-sessioner kör i Anthropics moln och kan inte se den här
# datorns hemkatalog över huvud taget — bara mappar du uttryckligen delar med
# sessionen. Cowork hämtar sin skill-lista från ditt CLAUDE-KONTO vid
# sessionsstart.
#
# Det betyder att en skill-ändring måste spridas åt TVÅ håll:
#   1. Claude Code  → det här scriptet (~/.claude/skills/)
#   2. Cowork       → manuell uppladdning under Customize → Skills
#
# Glöms steg 2 kör Cowork vidare på en gammal version utan att säga något.
# Skydd mot det finns numera i själva skillsen: SKILL_VERSION-stämpeln överst
# i varje SKILL.md, som jämförs mot repo-kopian vid start.
#
# Projekt-versionerna i .claude/skills/ är "source of truth" (versioneras i git).
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
echo "→ Claude Code plockar upp dem direkt."
echo ""
echo "⚠️  COWORK ÄR INTE UPPDATERAT AV DET HÄR."
echo "    Cowork läser skills från ditt Claude-konto, inte från den här datorn."
echo "    Ladda upp ändrade skills under Customize → Skills i Claude-appen,"
echo "    ersätt den befintliga posten (skapa inte en dubblett), och starta"
echo "    en NY Cowork-session — listan hämtas vid sessionsstart."
echo ""
echo "    Skills i det här projektet och deras version:"
for skill_dir in "$SOURCE_DIR"/*/; do
  [[ -d "$skill_dir" ]] || continue
  v=$(grep -m1 -o 'SKILL_VERSION: [0-9-]*' "$skill_dir/SKILL.md" 2>/dev/null | cut -d' ' -f2)
  echo "      - $(basename "$skill_dir")  ${v:-<ingen SKILL_VERSION>}"
done
