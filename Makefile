.PHONY: up down backend-test backend-lint frontend-build validate

up:
	docker compose up --build

down:
	docker compose down

backend-test:
	cd backend && pytest -q

backend-lint:
	cd backend && ruff check app tests

frontend-build:
	cd frontend && npm run build

validate: backend-lint backend-test frontend-build
	docker compose config --quiet
