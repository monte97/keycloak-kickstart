# Architecture — keycloak-kickstart

Technical reference for contributors and operators. Covers component design, Docker stack, init container pipeline, seed format, and key design decisions.

## Overview

keycloak-kickstart is a self-contained Docker Compose stack that brings up a production-ready Keycloak 26.x instance and configures it automatically from a declarative YAML seed file. No manual admin console steps are required after `docker compose up`.

Three capabilities:

1. **Stack provisioning** — Keycloak 26.x + PostgreSQL 16, wired and health-checked
2. **Provider installation** — SPI JARs are baked into the image at build time via a multi-stage Dockerfile
3. **Realm configuration** — a Python init container reads a seed YAML and idempotently applies all configuration via the Keycloak Admin API

---

## Component map

```
docker compose up
      │
      ├─ keycloak-db (PostgreSQL 16)
      │      healthcheck: pg_isready every 5s
      │
      ├─ keycloak (Keycloak 26.1)
      │      depends_on: keycloak-db (healthy)
      │      build: multi-stage Dockerfile
      │        stage 1: copy provider JARs → kc.sh build
      │        stage 2: copy built KC, EXPOSE 8080
      │      KC_HTTP_RELATIVE_PATH: /auth
      │
      └─ keycloak-init (Python init container)
             depends_on: keycloak
             restart: on-failure
             │
             ├─ seed_loader.py    — load + validate + interpolate YAML
             ├─ orchestrator.py   — wait for KC, drive configuration sequence
             └─ keycloak_client.py — idempotent Admin API wrapper
```

The init container exits with code 0 when all configuration is applied. Because it is `restart: on-failure`, it will retry if Keycloak is not yet accepting requests. Successful configuration is idempotent — re-running is safe.

---

## Docker stack

### Services

| Service | Image | Purpose |
|---------|-------|---------|
| `keycloak` | Custom build (Dockerfile) | Keycloak with providers pre-installed |
| `keycloak-db` | `postgres:16` | Persistent storage for Keycloak data |
| `keycloak-init` | Custom build (init/Dockerfile) | One-shot configuration via Admin API |

### Key environment variables

| Variable | Default | Description |
|----------|---------|-------------|
| `KC_ADMIN_USER` | `admin` | Bootstrap admin username |
| `KC_ADMIN_PASSWORD` | required | Bootstrap admin password |
| `KC_DB_USERNAME` | required | PostgreSQL username |
| `KC_DB_PASSWORD` | required | PostgreSQL password |
| `KC_PORT` | `8080` | Host port to expose Keycloak |
| `KC_HEALTHCHECK_TIMEOUT` | `300` | Seconds to wait for KC readiness |

All variables are read from `.env` (not committed — copy from `.env.example`).

### Volume

`keycloak-db-data` — named Docker volume. PostgreSQL data persists across `docker compose down`. Use `docker compose down -v` to wipe state completely.

---

## Dockerfile — multi-stage build

```
Stage 1 (builder):
  FROM quay.io/keycloak/keycloak:26.1 as builder
  COPY provider/*.jar  →  /opt/keycloak/providers/
  RUN kc.sh build      →  compiles theme, validates providers, creates optimized server

Stage 2 (runtime):
  FROM quay.io/keycloak/keycloak:26.1
  COPY --from=builder /opt/keycloak/ /opt/keycloak/
  ENTRYPOINT kc.sh start
```

**Why two stages?** `kc.sh build` compiles the server against the installed providers — this is required for JPA entity providers (like the webhook provider) to register their entities with Hibernate. The compiled artifact is then copied into a clean runtime image. The builder stage adds no bloat to the final image.

**Adding a provider:** place the JAR in `provider/` and rebuild the image. The `kc.sh build` step handles the rest.

---

## Init container pipeline

### Step 0: Seed loading (`seed_loader.py`)

1. Read YAML file at `SEED_FILE` (default `/app/seed.yml`)
2. Interpolate `${VAR}` and `${VAR:-default}` patterns recursively throughout the entire document
3. Validate structure (see [Seed validation](#seed-validation))
4. Return a plain Python dict

### Step 1: Readiness wait (`orchestrator.py`)

Poll `GET /auth/realms/master` every 5 seconds until HTTP 200 or `KC_HEALTHCHECK_TIMEOUT` elapsed. This is necessary because Keycloak performs schema migration and provider registration on first boot, which can take 30–120 seconds depending on hardware.

### Step 2: Configuration sequence (`orchestrator.py`)

For each realm in the seed, in this order:

```
1. ensure_realm(name)
2. configure_ssl(ssl_required)           — if present
3. ensure_client(clientId, ...)          — per client
   └── ensure_role(role_name)            — per role
4. ensure_group(group_name)              — per group
5. ensure_user(username, password)       — per user
   ├── assign_role_to_user(role)         — per role
   └── add_user_to_group(group)          — per group
6. configure_smtp(smtp_config)           — if present
7. configure_theme(theme_name)           — if present
8. configure_events(realm)              — if webhooks defined (enables ext-event-webhook listener)
9. register_webhook(url, events)         — per webhook
```

The order matters: clients must exist before roles can be created; roles and groups must exist before they can be assigned to users; `configure_events` must run before `register_webhook` (it enables the webhook event listener SPI).

### Step 3: Idempotency

Every operation in `keycloak_client.py` checks whether the resource already exists before creating it:

- Realm: `GET /realms` → skip if name present
- Client: `get_clients()` → skip if `clientId` matches
- Role: `get_client_roles()` → skip if `name` matches
- Group: `get_groups()` → skip if `name` matches
- User: `get_users(query={"username": ..., "exact": True})` → skip if found
- Webhook: `GET /webhooks/` → skip if URL + eventTypes identical; delete + recreate if URL matches but events differ

This means `docker compose up` can be run repeatedly without duplicating configuration.

---

## `keycloak_client.py` — Admin API wrapper

Thin wrapper over [python-keycloak](https://python-keycloak.readthedocs.io/) (`KeycloakAdmin`). Adds idempotency and logging to each operation.

### Authentication

Uses `KeycloakAdmin` with master realm credentials. The `access_token` is retrieved via `self._admin.connection.token["access_token"]` for direct REST calls (webhook endpoints, which are not part of the standard Admin API).

### Realm switching

`_switch_realm(realm_name)` sets `self._admin.realm_name` before each call. python-keycloak reuses the same HTTP session and re-authenticates automatically when the token expires.

### Webhook registration

The webhook provider exposes its own REST API at `/realms/{realm}/webhooks/`. The init container calls it directly with a bearer token rather than through python-keycloak (which has no built-in webhook support). Idempotency: if a webhook with the same URL exists and has the same event types, it is skipped; if the event types differ, the old webhook is deleted and recreated.

---

## Seed format

Complete reference: `init/seeds/example.yml`

### Minimal seed

```yaml
realms:
  - name: my-realm
    clients:
      - clientId: my-app
        app_url: "http://localhost:3000"
```

### Full seed structure

```yaml
realms:
  - name: my-realm
    ssl_required: "NONE"          # NONE | EXTERNAL | ALL
    theme: custom-theme           # must be installed in providers/

    smtp:
      host: smtp.example.com
      port: 587
      username: user
      password: secret
      ssl: false
      starttls: true
      sender: noreply@example.com

    clients:
      - clientId: my-app
        app_url: "http://localhost:3000"
        public_client: true
        direct_access_grants: true
        roles: [Admin, User]
        backchannel_logout_url: "http://api:8090/logout"
        disable_frontchannel_logout: true

    groups:
      - name: engineers
      - name: viewers

    users:
      - username: alice
        password: "${ALICE_PASSWORD:-secret}"
        temporary: false
        roles: [Admin]
        groups: [engineers]

    webhooks:
      - url: "http://listener:8888/webhook"
        events:
          - access.LOGIN
          - admin.USER-CREATE

    user_attributes:
      - name: language
        display_name: Language
        permissions:
          view: [admin, user]
```

### Seed validation

`validate_seed()` enforces:

- At least one realm with a `name`
- At least one client per realm (required by Keycloak's OIDC model)
- User `roles` reference roles defined in `clients[*].roles`
- User `groups` reference groups defined in `groups[*].name`

Invalid seeds cause the init container to exit with a descriptive error before making any API calls.

### Environment variable interpolation

Two patterns are supported in any string value:

| Pattern | Behavior |
|---------|----------|
| `${VAR}` | Requires `VAR` to be set; raises `ValueError` if missing |
| `${VAR:-default}` | Uses `default` if `VAR` is not set |

Interpolation is applied recursively to all string values in the seed — keys, nested objects, and list items. Non-string values (booleans, integers) pass through unchanged.

---

## Events and webhook integration

When a realm's seed includes `webhooks`, the init container enables two things:

1. **`configure_events()`** — sets `eventsListeners` to include `ext-event-webhook` (the SPI listener from keycloak-webhook-provider) and enables all event types on the realm
2. **`register_webhook()`** — POSTs each webhook to the provider's REST API with its URL and event filter list

The webhook provider SPI (`ext-event-webhook`) is registered in Keycloak at startup because its JAR is installed in `providers/` and compiled into the image. The init container only needs to activate it per realm and register the endpoint targets.

---

## Design decisions

### Why a Python init container instead of Keycloak import?

Keycloak supports realm import via `--import-realm` at startup. Two problems:

1. Import is not idempotent — it fails or overwrites if the realm already exists
2. Import requires the full realm JSON, which is verbose and not designed for templating

The init container approach is declarative (YAML, not JSON), idempotent, and uses env var interpolation naturally. It also survives provider registration timing issues — because it waits for KC readiness, it does not depend on import order.

**Trade-off:** the Admin API round-trips add 2–10 seconds to first boot. Acceptable for a one-shot init.

### Why python-keycloak instead of raw requests?

python-keycloak handles token acquisition and renewal automatically. The alternative (raw `requests` throughout) would require manual token management and retry logic. Direct `requests` calls are used only for webhook registration, which is outside the standard Admin API surface.

**Trade-off:** adds a third-party dependency. python-keycloak is well-maintained and widely used.

### Why `restart: on-failure` on the init container?

Keycloak's startup time is non-deterministic — it can take 30s on a fast machine or 2+ minutes on a slow VM. Rather than hard-coding a sleep or a fixed wait, the init container polls until KC is ready and then exits with 0. If KC is not ready within the timeout, the container exits with 1 and Docker restarts it. This avoids a fragile `sleep` and handles transient startup failures gracefully.

### Why mount `seed.yml` as a volume (not bake into image)?

The seed file changes per customer/deployment. Mounting it at runtime means a single image can serve multiple environments without rebuilding. The image itself is environment-agnostic; all customization lives in `seed.yml` and `.env`.

### Why `KC_HTTP_RELATIVE_PATH: /auth`?

Keycloak 17+ removed the `/auth` prefix by default, but many client libraries and tutorials still expect it. Setting it explicitly avoids confusion and maintains compatibility with the existing documentation and seed examples that reference `/auth/realms/...`.

---

## Operational considerations

### First boot

```
docker compose up
```

Expected sequence:
1. PostgreSQL starts and becomes healthy (~5s)
2. Keycloak starts, runs Liquibase migration, registers providers (~30–90s)
3. Init container waits for `GET /auth/realms/master` to return 200
4. Init container applies seed configuration (~2–10s per realm)
5. Init container exits with 0

Watch init container logs: `docker compose logs -f keycloak-init`

### Re-running after changes

Modify `seed.yml`, then:

```bash
docker compose up keycloak-init
```

The init container will re-run and apply only the delta (all operations are idempotent).

### Resetting state

```bash
docker compose down -v   # removes keycloak-db-data volume
docker compose up
```

This is a full reset: all realms, users, and configuration are wiped.

### Adding a provider JAR

1. Place the JAR in `provider/`
2. Rebuild and restart:

```bash
docker compose build keycloak
docker compose up -d keycloak
```

The `kc.sh build` step runs automatically during image build.

### Upgrading Keycloak

Update the `FROM` tag in `Dockerfile` and `docker-compose.yml`:

```dockerfile
FROM quay.io/keycloak/keycloak:26.2 as builder
```

Then rebuild:

```bash
docker compose build
docker compose up -d keycloak
```

Liquibase migrations run automatically on startup.
