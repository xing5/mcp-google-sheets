.DEFAULT_GOAL = help

.PHONY: build
build: ## Build container image.
	docker compose build

.PHONY: start
start: ## Spin up container.
	docker compose up -d

.PHONY: down
down: ## Stop and remove container.
	docker compose down

.PHONY: restart
restart: ## Restart container (requires Claude Code restart to reconnect SSE).
	docker compose restart mcp-google-sheets

.PHONY: recreate
recreate: ## Recreate container from scratch (removes historical logs).
	docker compose up -d --force-recreate

.PHONY: logs
logs: ## Tail container logs.
	docker compose logs -f

.PHONY: sh
sh: ## Open a shell in the container.
	docker compose exec mcp-google-sheets bash

# Self-documenting help
# https://www.freecodecamp.org/news/self-documenting-makefile/
.PHONY: help
help: ## Show this help.
	@egrep -h '\s##\s' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-16s\033[0m %s\n", $$1, $$2}'
