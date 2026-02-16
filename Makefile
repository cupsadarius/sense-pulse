.PHONY: up down logs build restart status test-poll shell-redis

up:
	docker compose up -d

down:
	docker compose down

logs:
	docker compose logs -f

build:
	docker compose build

restart:
	docker compose restart

status:
	docker compose ps

test-poll:
	docker compose --profile poll run --rm source-weather

shell-redis:
	docker compose exec redis redis-cli
