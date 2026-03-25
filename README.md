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

The image includes `keycloak-webhook-provider-1.0.0-SNAPSHOT.jar`, a custom SPI provider with HMAC-signed webhook delivery, retry with exponential backoff, circuit breaker, full REST API, and an embedded admin UI.

### Admin UI

```
http://localhost:8080/auth/realms/{realm}/webhooks/ui
```

Create, edit, and delete webhooks, monitor circuit breaker state, and send test pings — all from the browser. Authentication uses the realm's Keycloak JS adapter.

### REST API

```
http://localhost:8080/auth/realms/{realm}/webhooks
```

Requires `view-events` / `manage-events` realm permissions. See `docs/PROJECT_STATUS.md` for the full endpoint list.

## Architecture

| Service | Description |
|---|---|
| `keycloak` | Keycloak 26.1 with custom event provider |
| `keycloak-db` | PostgreSQL 18 for Keycloak storage |
| `keycloak-init` | Python one-shot container that configures realms from `seed.yml` |
