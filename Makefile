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
	$(COMPOSE) run --rm -v $(CURDIR)/scripts:/app/scripts backend python /app/scripts/seed.py

check-0:
	curl --fail --silent --show-error http://localhost:8000/health
	$(MAKE) test
	$(MAKE) lint

check-1:
	$(MAKE) seed
	$(MAKE) seed
	$(MAKE) test
	$(MAKE) lint

check-2:
	$(MAKE) test
	$(MAKE) lint

check-3:
	$(MAKE) seed
	$(MAKE) test
	$(MAKE) lint

check-4:
	$(MAKE) seed
	$(MAKE) test
	$(MAKE) lint

check-%:
	@echo "check-$* is not implemented until its phase."
	@exit 1
