.PHONY: up down backend-test backend-lint retrieval-quality frontend-build validate

up:
	docker compose up --build

down:
	docker compose down

backend-test:
	cd backend && PYTHONPATH=. python -m pytest -q

backend-lint:
	cd backend && PYTHONPATH=. python -m ruff check app tests

retrieval-quality:
	cd backend && PYTHONPATH=. python scripts/evaluate_retrieval.py --dataset eval/retrieval-quality-v1.json --output retrieval-quality-report.json --min-recall 0.80 --min-mrr 0.80 --min-ndcg 0.80 --min-citation-hit-rate 0.80 --require-hybrid-not-worse

frontend-build:
	cd frontend && npm run build

validate: backend-lint backend-test retrieval-quality frontend-build
	ZKB_API_KEY=$${ZKB_API_KEY:-local-validation-secret} docker compose config --quiet
