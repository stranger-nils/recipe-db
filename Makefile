# Local dev workflow for recipe-db.
#
# Spår A — kodändringar:
#   make pull-prod   Drar ner prod-databasen + uploads till ./data/ via rsync
#                    (gör en .bak av befintlig local DB först).
#   make dev         pull-prod + docker compose up --build (Flask på :5001).
#   make logs        Tail på containerns loggar.
#   make dev-down    docker compose down.
#   make ship        Pushar master → GHA deployar till VPS.
#
# Spår B — dataändringar (recept) hanteras via recipe/edit-recipe-skillarna.

VPS         ?= minvps
VPS_APP_DIR ?= /opt/recipe-db
LOCAL_DATA  := ./data

.PHONY: help pull-prod pull-db pull-uploads dev dev-down logs ship status

help:
	@awk '/^# / {sub(/^# ?/,""); print; next} /^[a-zA-Z_-]+:/ {print "  " $$0}' Makefile

pull-db:
	@# Guard: docker compose creates the bind-mount target as a *directory*
	@# if it's missing on first compose-up. Bail loudly instead of rsync'ing
	@# the file inside it.
	@if [ -d $(LOCAL_DATA)/recipe.db ]; then \
		echo "✗ $(LOCAL_DATA)/recipe.db is a directory (Docker bind-mount artefact)."; \
		echo "  Run: rm -rf $(LOCAL_DATA)/recipe.db   then retry."; \
		exit 1; \
	fi
	@echo "→ Snapshotting local DB to .bak before overwrite"
	@if [ -f $(LOCAL_DATA)/recipe.db ]; then \
		cp $(LOCAL_DATA)/recipe.db $(LOCAL_DATA)/recipe.db.bak.$$(date -u +%Y%m%dT%H%M%SZ); \
	fi
	@echo "→ Rsyncing prod DB from $(VPS):$(VPS_APP_DIR)/data/recipe.db"
	rsync -avz --progress $(VPS):$(VPS_APP_DIR)/data/recipe.db $(LOCAL_DATA)/recipe.db

pull-uploads:
	@echo "→ Rsyncing uploads from $(VPS):$(VPS_APP_DIR)/data/uploads/"
	rsync -avz --delete $(VPS):$(VPS_APP_DIR)/data/uploads/ $(LOCAL_DATA)/uploads/

pull-prod: pull-db pull-uploads
	@echo "✓ Local mirror synced from prod"

dev: pull-prod
	docker compose up --build -d
	@echo "✓ http://localhost:5001"

dev-down:
	docker compose down

logs:
	docker compose logs -f recipe-db

status:
	@git status --short
	@echo "---"
	@git log --oneline origin/master..HEAD || true

ship:
	@if [ -n "$$(git status --porcelain)" ]; then \
		echo "✗ Working tree not clean. Commit or stash first."; \
		git status --short; \
		exit 1; \
	fi
	@if [ "$$(git rev-parse --abbrev-ref HEAD)" != "master" ]; then \
		echo "✗ Not on master (on $$(git rev-parse --abbrev-ref HEAD)). Switch first."; \
		exit 1; \
	fi
	@echo "→ Pushing to origin/master (GHA deploy will trigger)"
	git push origin master
	@echo "✓ Pushed. Watch: gh run watch  (or check GitHub Actions UI)"
