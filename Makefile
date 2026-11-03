COMPOSE := docker compose

.PHONY: up down test lint seed evidence check-0 check-7 check-8 check-%

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

check-5:
	$(MAKE) seed
	$(MAKE) test
	$(MAKE) lint

check-6:
	$(MAKE) seed
	$(MAKE) test
	$(MAKE) lint

check-7:
	$(MAKE) seed
	$(MAKE) test
	$(MAKE) lint
	cd frontend && npm run build
	cd frontend && npm run lint
	cd frontend && npm test

evidence:
	$(COMPOSE) run --rm -v $(CURDIR)/docs:/app/docs -v $(CURDIR)/scripts:/app/scripts backend python /app/scripts/generate_test_evidence.py

check-8:
	$(MAKE) test
	$(COMPOSE) run --rm backend pytest --cov=app/services --cov-fail-under=85 --cov-report=term-missing
	$(MAKE) evidence
	$(MAKE) lint

check-%:
	@echo "check-$* is not implemented until its phase."
	@exit 1
