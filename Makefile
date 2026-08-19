.PHONY: up down backend-test backend-lint frontend-build validate

up:
	docker compose up --build

down:
	docker compose down

backend-test:
	cd backend && PYTHONPATH=. python -m pytest -q

backend-lint:
	cd backend && PYTHONPATH=. python -m ruff check app tests

frontend-build:
	cd frontend && npm run build

validate: backend-lint backend-test frontend-build
	ZKB_API_KEY=$${ZKB_API_KEY:-local-validation-secret} docker compose config --quiet
