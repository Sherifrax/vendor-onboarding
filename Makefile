COMPOSE := docker compose

.PHONY: up down test lint seed check-0 check-%

up:
	$(COMPOSE) up --build -d

down:
	$(COMPOSE) down

test:
	$(COMPOSE) run --rm backend pytest

lint:
	$(COMPOSE) run --rm backend ruff check .
	$(COMPOSE) run --rm backend ruff format --check .

seed:
	@echo "Seed data is introduced in Phase 1."
	@exit 1

check-0:
	curl --fail --silent --show-error http://localhost:8000/health
	$(MAKE) test
	$(MAKE) lint

check-%:
	@echo "check-$* is not implemented until its phase."
	@exit 1
