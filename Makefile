.PHONY: up down restart build logs ps clean health test fetch-provider help

KC_URL := http://localhost:$${KC_PORT:-8080}/auth
PROVIDER_DIR := ./provider
WEBHOOK_REPO := monte97/keycloak-webhook-provider

## fetch-provider  Download latest keycloak-webhook-provider JAR from GitHub
fetch-provider:
	@echo ">>> Fetching latest keycloak-webhook-provider release..."
	@RELEASE=$$(curl -sf https://api.github.com/repos/$(WEBHOOK_REPO)/releases/latest | grep '"tag_name"' | cut -d'"' -f4); \
	VERSION=$${RELEASE#v}; \
	JAR="keycloak-webhook-provider-$${VERSION}.jar"; \
	if [ -f "$(PROVIDER_DIR)/$$JAR" ]; then \
		echo "  Already up to date: $$JAR"; \
	else \
		echo "  Downloading $$JAR..."; \
		rm -f $(PROVIDER_DIR)/keycloak-webhook-provider-*.jar; \
		curl -fL "https://github.com/$(WEBHOOK_REPO)/releases/download/$$RELEASE/$$JAR" \
			-o "$(PROVIDER_DIR)/$$JAR"; \
		echo "  Done: $$JAR"; \
	fi

## up         Start the stack (downloads latest provider if needed)
up: fetch-provider
	docker compose up -d

## down       Stop the stack
down:
	docker compose down

## restart    Restart all services
restart:
	docker compose restart

## build      Rebuild images and start
build:
	docker compose up --build -d

## logs       Tail all logs
logs:
	docker compose logs -f

## ps         Show running services
ps:
	docker compose ps

## health     Check Keycloak and PostgreSQL status
health:
	@echo ">>> Keycloak..."
	@curl -sf "$(KC_URL)/realms/master" > /dev/null 2>&1 \
		&& echo "  Keycloak: OK" || echo "  Keycloak: UNREACHABLE"
	@echo ">>> PostgreSQL..."
	@docker exec keycloak-db pg_isready -U $$(docker exec keycloak-db printenv POSTGRES_USER) > /dev/null 2>&1 \
		&& echo "  PostgreSQL: OK" || echo "  PostgreSQL: UNREACHABLE"
	@echo ">>> Init container..."
	@STATUS=$$(docker inspect -f '{{.State.Status}}' keycloak-init 2>/dev/null); \
	EXIT=$$(docker inspect -f '{{.State.ExitCode}}' keycloak-init 2>/dev/null); \
	if [ "$$STATUS" = "exited" ] && [ "$$EXIT" = "0" ]; then \
		echo "  Init: COMPLETED (exit 0)"; \
	elif [ "$$STATUS" = "running" ]; then \
		echo "  Init: RUNNING (still configuring)"; \
	else \
		echo "  Init: $$STATUS (exit $$EXIT)"; \
	fi

## test       Run init container unit tests
test:
	cd init && python -m pytest -v

## clean      Stop and remove all data (full reset)
clean:
	docker compose down -v

## help       Show available targets
help:
	@grep -E '^## ' Makefile | sed 's/^## /  make /'
