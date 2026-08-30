#!/usr/bin/env bash
#
# publish-plan.sh — rendera veckomenyer och publicera dem på Raspberry Pi:n.
#
# Körs från Macen (kräver tailscale + ssh-nyckel till Pi:n). Cowork-sandboxen
# ligger inte på tailnetet och kan inte köra det här skriptet — den skriver
# bara plans/<slug>.json, sedan tar det här skriptet vid.
#
# Idempotent: kör om så ofta du vill. Renderar om HTML från JSON och rsync:ar.
# Inget raderas på Pi:n om du inte uttryckligen ber om det med --prune.
#
# Struktur på Pi:n:
#   /srv/veckomeny/index.html          översikt över publicerade veckor
#   /srv/veckomeny/<slug>.html         en veckomeny
#   /srv/veckomeny/plans/<slug>.json   rådata
#
# Användning:
#   scripts/publish-plan.sh                 # rendera om allt + publicera
#   scripts/publish-plan.sh 2026-w36        # bara en vecka (+ index)
#   scripts/publish-plan.sh --dry-run
#   scripts/publish-plan.sh --host annan-pi --dest /srv/veckomeny
#   scripts/publish-plan.sh --prune         # spegla exakt; raderar borttagna veckor
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLANS_DIR="${PLANS_DIR:-$REPO_ROOT/plans}"
HOST="${VECKOMENY_HOST:-nils-rpi}"
DEST="${VECKOMENY_DEST:-/srv/veckomeny}"
# Basadress för utskrift. Porten är 8443 eftersom 443 på Pi:n redan används
# av OpenClaw-gatewayen. Sätt VECKOMENY_URL i .claude/.env för det fullständiga
# tailnet-namnet (det hör inte hemma i git).
BASE_URL="${VECKOMENY_URL:-https://nils-rpi:8443}"
DRY_RUN=""
PRUNE=""
SLUGS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host)      HOST="$2"; shift 2 ;;
    --dest)      DEST="$2"; shift 2 ;;
    --plans-dir) PLANS_DIR="$2"; shift 2 ;;
    --dry-run)   DRY_RUN="--dry-run"; shift ;;
    --prune)     PRUNE="--delete"; shift ;;
    -h|--help)   sed -n '2,26p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    -*)          echo "Okänd flagga: $1" >&2; exit 2 ;;
    *)           SLUGS+=("$1"); shift ;;
  esac
done

say(){ printf '%s\n' "$*"; }
die(){ printf 'FEL: %s\n' "$*" >&2; exit 1; }

command -v rsync >/dev/null || die "rsync saknas."
command -v python3 >/dev/null || die "python3 saknas."
[[ -d "$PLANS_DIR" ]] || die "Hittar ingen plans-katalog: $PLANS_DIR"

# --- 1. rendera -------------------------------------------------------------
if [[ ${#SLUGS[@]} -gt 0 ]]; then
  targets=()
  for slug in "${SLUGS[@]}"; do
    json="$PLANS_DIR/${slug%.json}.json"
    [[ -f "$json" ]] || die "Hittar ingen plan: $json"
    targets+=("$json")
  done
  python3 "$REPO_ROOT/scripts/build_plan_page.py" --plans-dir "$PLANS_DIR" "${targets[@]}"
else
  shopt -s nullglob
  any=("$PLANS_DIR"/*.json)
  shopt -u nullglob
  [[ ${#any[@]} -gt 0 ]] || die "Inga planer att publicera i $PLANS_DIR"
  python3 "$REPO_ROOT/scripts/build_plan_page.py" --plans-dir "$PLANS_DIR" --all
fi

# --- 2. nåbarhet ------------------------------------------------------------
say ""
say "Kontrollerar $HOST ..."
ssh -o BatchMode=yes -o ConnectTimeout=8 "$HOST" true 2>/dev/null \
  || die "Når inte $HOST över ssh. Är tailscale uppe (tailscale status) och nyckeln utlagd?"

# Katalogerna skapas vid behov — gör skriptet körbart på en färsk Pi.
ssh "$HOST" "mkdir -p '$DEST/plans'" \
  || die "Kunde inte skapa $DEST/plans på $HOST (rättigheter? se docs/pi-setup.md)"

# --- 3. synka ---------------------------------------------------------------
say "Publicerar → $HOST:$DEST"
# Inget --chmod och inget -p: Apples rsync (2.6.9) kan inte --chmod, och -p
# skulle släpa med repots filrättigheter till servern. Utan -p sätts nya filer
# av fjärrsidans umask, och chmod-steget nedan garanterar resten.
# shellcheck disable=SC2086
rsync -rltv $DRY_RUN $PRUNE \
  --include='*.html' --exclude='*' \
  "$PLANS_DIR"/ "$HOST:$DEST/"
# shellcheck disable=SC2086
rsync -rltv $DRY_RUN $PRUNE \
  --include='*.json' --exclude='*' \
  "$PLANS_DIR"/ "$HOST:$DEST/plans/"

# Läsbart för webbservern. a+rX = läs för alla, traversering bara på kataloger.
if [[ -z "$DRY_RUN" ]]; then
  ssh "$HOST" "chmod -R a+rX '$DEST'" \
    || die "Filerna kopierades men chmod misslyckades — Caddy kan sakna läsrätt."
fi

say ""
if [[ -n "$DRY_RUN" ]]; then
  say "Torrkörning — inget skrevs."
else
  say "Klart. Öppna $BASE_URL/ på en enhet i tailnetet."
  say "(Serveras inte? Kör igenom docs/pi-setup.md på $HOST.)"
fi
