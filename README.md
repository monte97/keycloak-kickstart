# keycloak-kickstart

Opinionated Keycloak setup with automated realm initialization. Clone, configure, `docker compose up`.

## Quickstart

```bash
cp .env.example .env                    # edit credentials
cp init/seeds/example.yml seed.yml      # edit realm/clients/users
docker compose up
```

Keycloak will be available at `http://localhost:8080/auth` (or the port set in `.env`).

## Seed File

The init container reads a YAML seed file to configure Keycloak on first boot. Copy `init/seeds/example.yml` to `seed.yml` at the project root and customize it.

The seed supports environment variable interpolation:

- `${VAR}` — required, error if missing
- `${VAR:-default}` — optional, uses default if missing

See `init/seeds/example.yml` for all supported fields: realms, clients, roles, groups, users, SMTP, webhooks, user attributes, logout configuration, and admin password reset.

## Custom Theme

This kickstart does not include a custom theme. To add one:

1. Create your theme under `themes/<name>/login/` following the [Keycloak theme documentation](https://www.keycloak.org/docs/latest/server_development/#_themes)
2. Add to `Dockerfile` before the `RUN` build step:
   ```dockerfile
   COPY ./themes/<name>/ /opt/keycloak/themes/<name>/
   ```
3. Set `theme: <name>` in your `seed.yml`

## Events & Webhooks

The image includes [keycloak-webhook-provider](https://github.com/monte97/keycloak-webhook-provider), a custom SPI with HMAC-signed webhook delivery, retry with exponential backoff, circuit breaker, REST API, and an embedded admin UI.

Configure webhooks in your seed file:

```yaml
webhooks:
  - url: "http://your-service/webhook"
    events:
      - access.LOGIN
      - access.LOGOUT
      - admin.USER-DELETE
```

Admin UI: `http://localhost:8080/auth/realms/{realm}/webhooks/ui`

REST API: `http://localhost:8080/auth/realms/{realm}/webhooks` (requires `view-events` / `manage-events` role)

## Architecture

| Service | Description |
|---|---|
| `keycloak` | Keycloak 26.1 with webhook provider |
| `keycloak-db` | PostgreSQL 18 for Keycloak storage |
| `keycloak-init` | Python one-shot container that configures realms from `seed.yml` |

## Makefile

```
make up       Start the stack
make down     Stop the stack
make build    Rebuild and start
make logs     Tail logs
make ps       Show running services
make clean    Stop and remove volumes (full reset)
```

## License

MIT — Copyright (c) 2026 Francesco Montelli

---

Built by [Francesco Montelli](https://montelli.dev) · Part of the [Keycloak SSO Setup](https://montelli.dev/servizi/keycloak) productized service
