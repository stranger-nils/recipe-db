# Local dev workflow for recipe-db.
#
# Spår A — kodändringar:
#   make dev         docker compose up --build (Flask på :5001) mot lokal ./data/.
#   make logs        Tail på containerns loggar.
#   make dev-down    docker compose down.
#   make ship        Pushar master till GitHub. Deployar INGENTING — appen på
#                    Pi:n (nils-rpi) deployas via PR i stranger-nils/iris-workspace
#                    som Iris rullar ut efter merge.
#
# Spår B — dataändringar (recept) hanteras via recipe/edit-recipe-skillarna,
# som skriver till Pi:ns databas via HTTP-API:t.
#
# `make pull-prod` (rsync från VPS:en minvps) är borttaget: prod ligger på Pi:n,
# det finns ingen SSH dit och ingen export-endpoint. Läs prod via API:t.

LOCAL_DATA  := ./data

.PHONY: help dev dev-down logs ship status

help:
	@awk '/^# / {sub(/^# ?/,""); print; next} /^[a-zA-Z_-]+:/ {print "  " $$0}' Makefile

dev:
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
	@echo "→ Pushing to origin/master (no deploy — Pi deploys via iris-workspace PR)"
	git push origin master
	@echo "✓ Pushed."
