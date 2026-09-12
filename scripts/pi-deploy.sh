#!/bin/bash
# Idempotent deploy av recipe-db som Docker-container på nils-rpi.
# Körs från värden (inte inuti OpenClaw-containern): 
#   bash /home/nilslunden/docker/openclaw/data/workspace/recipe-db/scripts/pi-deploy.sh
set -euo pipefail

cd "$(dirname "$0")/.."
REPO="$(pwd)"
echo "== recipe-db container-deploy ($(hostname)) =="

# 1. Säkerställ att datakataloger finns (bind-mounts i compose).
mkdir -p data/backups data/uploads

# 2. Bygg & starta containern (LAN-bind via docker-compose.rpi.yml).
docker compose -f docker-compose.rpi.yml up -d --build

# 3. Hälsokontroll.
CODE=""
for _ in $(seq 1 20); do
  CODE="$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:5001/ || true)"
  [ "$CODE" = "200" ] && break
  sleep 1
done
echo "UI http://127.0.0.1:5001/ -> HTTP ${CODE:-timeout}"
if [ "$CODE" != "200" ]; then
  echo "Hälsokontroll misslyckades. Loggar:" >&2
  docker compose -f docker-compose.rpi.yml logs --tail 40 >&2
  exit 1
fi

echo
echo "Klart. Nåbar via:"
echo "  Lokalt på RPi:n:  http://127.0.0.1:5001"
echo "  Från LAN/tailnet: http://192.168.0.106:5001"
echo "Ångra: docker compose -f docker-compose.rpi.yml down"