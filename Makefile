.PHONY: install test lint deploy

install:
	pip install -r requirements.txt -r requirements-dev.txt
	pre-commit install

test:
	pytest tests/

lint:
	ruff check src/ tests/
	ruff format --check src/ tests/

deploy:
	cd infra && cdk deploy --all --require-approval never
