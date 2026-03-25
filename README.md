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

The image includes two providers:

- **`keycloak-events-26.0.jar`** — event listener that enables webhook notifications configured via seed file
- **`keycloak-webhook-provider-1.0.0-SNAPSHOT.jar`** — custom SPI with REST API and embedded admin UI

### Seed-based configuration

Configure webhooks in your seed file (handled by `keycloak-events`):

```yaml
webhooks:
  - url: "http://your-service/webhook"
    events:
      - access.LOGIN
      - access.LOGOUT
      - admin.USER-DELETE
```

When webhooks are defined, the init container automatically enables event listeners and admin events for the realm.

### Admin UI

The custom webhook provider includes a React admin UI served directly from the JAR:

```
http://localhost:8080/auth/realms/{realm}/webhooks/ui
```

The UI lets you create, edit, and delete webhooks, monitor circuit breaker state, and send test pings — no Keycloak admin console required. Authentication uses the realm's Keycloak JS adapter.

The REST API is available at `http://localhost:8080/auth/realms/{realm}/webhooks` and requires `view-events` / `manage-events` realm permissions.

## Architecture

| Service | Description |
|---|---|
| `keycloak` | Keycloak 26.1 with custom event provider |
| `keycloak-db` | PostgreSQL 16 for Keycloak storage |
| `keycloak-init` | Python one-shot container that configures realms from `seed.yml` |
