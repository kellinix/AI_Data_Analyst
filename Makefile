# ============================================================
# AI Dashboard Generator — Makefile
# ============================================================

.PHONY: help dev prod down logs clean setup test lint format migrate seed

DOCKER_COMPOSE = docker compose
DOCKER_COMPOSE_PROD = docker compose -f docker-compose.prod.yml

# Colours
GREEN  := $(shell tput -Txterm setaf 2)
YELLOW := $(shell tput -Txterm setaf 3)
CYAN   := $(shell tput -Txterm setaf 6)
RESET  := $(shell tput -Txterm sgr0)

## help: Show this help message
help:
	@echo ''
	@echo '${CYAN}AI Dashboard Generator${RESET}'
	@echo ''
	@echo '${YELLOW}Usage:${RESET}'
	@grep -E '^## [a-zA-Z_-]+:' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":"}; {printf "  ${GREEN}make %-20s${RESET} %s\n", $$2, $$3}' | sed 's/## //'
	@echo ''

## setup: First-time project setup (copy .env, install deps)
setup:
	@echo "$(CYAN)Setting up project...$(RESET)"
	@test -f .env || (cp .env.example .env && echo "$(GREEN)Created .env from .env.example — please fill in your values$(RESET)")
	@cd frontend && npm install
	@echo "$(GREEN)Setup complete. Edit .env with your credentials, then run 'make dev'$(RESET)"

## dev: Start all services in development mode
dev:
	@echo "$(CYAN)Starting development environment...$(RESET)"
	$(DOCKER_COMPOSE) up --build -d
	@echo "$(GREEN)Services started:$(RESET)"
	@echo "  Frontend:  http://localhost:3000"
	@echo "  Backend:   http://localhost:8000"
	@echo "  API Docs:  http://localhost:8000/docs"
	@echo "  Flower:    http://localhost:5555"

## dev-logs: Start services with logs in foreground
dev-logs:
	$(DOCKER_COMPOSE) up --build

## prod: Start all services in production mode
prod:
	@echo "$(CYAN)Starting production environment...$(RESET)"
	$(DOCKER_COMPOSE_PROD) up --build -d

## down: Stop all services
down:
	$(DOCKER_COMPOSE) down

## down-prod: Stop production services
down-prod:
	$(DOCKER_COMPOSE_PROD) down

## down-volumes: Stop all services and remove volumes (DESTRUCTIVE)
down-volumes:
	@echo "$(YELLOW)WARNING: This will remove all data volumes!$(RESET)"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	$(DOCKER_COMPOSE) down -v

## logs: Follow all service logs
logs:
	$(DOCKER_COMPOSE) logs -f

## logs-backend: Follow backend logs
logs-backend:
	$(DOCKER_COMPOSE) logs -f backend

## logs-worker: Follow celery worker logs
logs-worker:
	$(DOCKER_COMPOSE) logs -f celery_worker

## migrate: Run Alembic database migrations
migrate:
	$(DOCKER_COMPOSE) exec backend alembic upgrade head

## migrate-create: Create a new migration (MSG=your message)
migrate-create:
	$(DOCKER_COMPOSE) exec backend alembic revision --autogenerate -m "$(MSG)"

## seed: Seed the database with sample data
seed:
	$(DOCKER_COMPOSE) exec backend python scripts/seed.py

## test: Run all tests
test: test-backend test-frontend

## test-backend: Run backend tests
test-backend:
	$(DOCKER_COMPOSE) exec backend pytest tests/ -v --tb=short

## test-frontend: Run frontend tests
test-frontend:
	$(DOCKER_COMPOSE) exec frontend npm test

## lint: Lint all code
lint: lint-backend lint-frontend

## lint-backend: Lint backend Python code
lint-backend:
	$(DOCKER_COMPOSE) exec backend ruff check app/
	$(DOCKER_COMPOSE) exec backend mypy app/

## lint-frontend: Lint frontend TypeScript code
lint-frontend:
	$(DOCKER_COMPOSE) exec frontend npm run lint

## format: Format all code
format: format-backend format-frontend

## format-backend: Format backend Python code
format-backend:
	$(DOCKER_COMPOSE) exec backend ruff format app/

## format-frontend: Format frontend TypeScript code
format-frontend:
	$(DOCKER_COMPOSE) exec frontend npm run format

## shell-backend: Open Python shell in backend container
shell-backend:
	$(DOCKER_COMPOSE) exec backend python

## shell-db: Open PostgreSQL shell
shell-db:
	$(DOCKER_COMPOSE) exec postgres psql -U $(POSTGRES_USER) -d $(POSTGRES_DB)

## shell-redis: Open Redis CLI
shell-redis:
	$(DOCKER_COMPOSE) exec redis redis-cli

## build: Build all Docker images
build:
	$(DOCKER_COMPOSE) build

## pull: Pull latest Docker images
pull:
	$(DOCKER_COMPOSE) pull

## ps: Show running services
ps:
	$(DOCKER_COMPOSE) ps

## clean: Remove all containers, images, and volumes
clean:
	@echo "$(YELLOW)WARNING: This will remove ALL Docker resources for this project!$(RESET)"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	$(DOCKER_COMPOSE) down -v --rmi local
	@echo "$(GREEN)Clean complete$(RESET)"

## health: Check health of all services
health:
	@echo "$(CYAN)Checking service health...$(RESET)"
	@./scripts/health_check.sh
