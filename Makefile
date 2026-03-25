.PHONY: up down restart build logs ps clean

up:
	docker compose up -d

down:
	docker compose down

restart:
	docker compose restart

build:
	docker compose up --build -d

logs:
	docker compose logs -f

ps:
	docker compose ps

clean:
	docker compose down -v
