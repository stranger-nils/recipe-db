#!/bin/bash
# Starta recipe-db (Docker-container) — idempotent
cd /root/.openclaw/workspace/recipe-db
if docker inspect recipe-db >/dev/null 2>&1 && [ "$(docker inspect -f '{{.State.Running}}' recipe-db 2>/dev/null)" = "true" ]; then
  echo "Already running: recipe-db ($(docker inspect -f '{{.State.Running}}' recipe-db))"
  exit 0
fi
if docker inspect recipe-db >/dev/null 2>&1; then
  docker start recipe-db
else
  docker run -d --name recipe-db --restart unless-stopped -p 5001:5001 \
    -v /home/nilslunden/docker/openclaw/data/workspace/recipe-db/data/recipe.db:/app/recipe.db \
    -v /home/nilslunden/docker/openclaw/data/workspace/recipe-db/data/uploads:/app/static/uploads \
    -v /home/nilslunden/docker/openclaw/data/workspace/recipe-db/data/backups:/app/backups \
    --env-file .env \
    -e DATABASE_URL=sqlite:///recipe.db -e BACKUP_DIR=/app/backups -e RECIPE_DB_PATH=/app/recipe.db \
    recipe-db:local
fi
sleep 2
curl -s -o /dev/null -w "recipe-db UI: HTTP %{http_code}\n" http://192.168.0.106:5001/