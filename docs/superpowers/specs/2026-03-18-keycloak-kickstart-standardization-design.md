# Keycloak Kickstart — Standardization Design

**Date:** 2026-03-18
**Status:** Approved

## Goal

Transform the current repo (derived from a client project) into a reusable, context-agnostic Keycloak kickstart template. Anyone can clone it, configure a seed YAML and `.env`, and spin up a fully initialized Keycloak instance with PostgreSQL.

## Approach

Surgical cleanup of the existing repo: remove client-specific artifacts, de-brand all references, fix broken tests, add docker-compose with full stack, add `.env.example`. The `keycloak-events/` directory is a separate project that produces the JAR — it is ignored by this spec (not modified, not removed).

## Repository Structure

```
keycloak-kickstart/
├── .gitignore                  # root gitignore (new)
├── Dockerfile                  # KC 26.1, provider JAR only (no theme)
├── docker-compose.yml          # KC + PostgreSQL + init container
├── .env.example                # all variables documented
├── init/
│   ├── .dockerignore           # unchanged (excludes seeds/)
│   ├── .gitignore              # unchanged (excludes .venv/)
│   ├── Dockerfile              # header comment de-branded
│   ├── orchestrator.py         # de-brand header + default KC_URL
│   ├── keycloak_client.py      # unchanged
│   ├── seed_loader.py          # unchanged
│   ├── requirements.txt        # unchanged
│   ├── seeds/
│   │   └── example.yml         # de-branded, theme line commented out
│   └── tests/
│       ├── test_init.py        # de-brand header, fix broken assertions
│       ├── test_keycloak_client.py  # rename "builder" realm to "test-realm"
│       └── test_seed_loader.py # unchanged
├── provider/
│   └── keycloak-events-26.0.jar  # JAR filename unchanged; compatible with KC 26.1
├── keycloak-events/            # separate project, NOT touched by this spec
└── README.md                   # rewritten, generic, references KC theme docs
```

## Changes from Current State

| File/Directory | Action | Details |
|---|---|---|
| `themes/` | **Remove entirely** | Client-specific assets; README links to official KC theme docs |
| `init/seeds/local.yml` | **Remove** | Client-specific seed data |
| `init/seeds/example.yml` | **Clean** | Remove header comment (line 1); comment out `theme: custom-theme` with note that custom themes require Dockerfile modification |
| `init/Dockerfile` | **Remove header comment** | Line 1 (`# rd-auth-server/init/Dockerfile`) |
| `Dockerfile` | **Update** | KC 26.1, remove `ARG KC_THEME` and `COPY ./themes/...` block |
| `init/orchestrator.py` | **De-brand** | Remove header comment (line 1: `# rd-auth-server/...`); change default `KC_URL` from `http://rd-auth-server:8080/auth` to `http://keycloak:8080/auth` |
| `init/keycloak_client.py` | **No change** | — |
| `init/seed_loader.py` | **No change** | — |
| `init/tests/test_init.py` | **Fix** | Remove header comment (line 1); remove broken assertions for `ensure_client_scope` and `create_scope_mapper` (methods don't exist); remove `scope` from test seed data |
| `init/tests/test_keycloak_client.py` | **De-brand** | Replace `"builder"` realm name with `"test-realm"` throughout |
| `init/tests/test_seed_loader.py` | **No change** | — |
| `README.md` | **Rewrite** | Generic description, quickstart, seed docs, theme link, events docs |
| `docker-compose.yml` | **Add** | Full stack: KC + PostgreSQL + init |
| `.env.example` | **Add** | All variables documented with sensible defaults |
| `.gitignore` (root) | **Add** | `.env`, `seed.yml`, `__pycache__/`, `*.pyc`, `.venv/` |
| `keycloak-events/` | **No change** | Separate project that produces the JAR; not part of this spec |

## Keycloak Version

Update from `26.0` to `26.1`. The `keycloak-events-26.0.jar` provider is compatible with KC 26.1 (Keycloak SPI compatibility is maintained within the 26.x line); the JAR filename is kept as-is.

## docker-compose.yml

Three services:

- **keycloak**: built from `Dockerfile`, exposed on `${KC_PORT:-8080}`, depends on DB health check. Environment includes:
  - `KC_BOOTSTRAP_ADMIN_USERNAME: ${KC_ADMIN_USER:-admin}` and `KC_BOOTSTRAP_ADMIN_PASSWORD: ${KC_ADMIN_PASSWORD}` (KC 26.1 names; `KEYCLOAK_ADMIN` was removed)
  - `KC_HTTP_RELATIVE_PATH: /auth` (restores the `/auth` context path, required for the init container's `KC_URL`)
  - `KC_DB: postgres`
  - `KC_DB_URL: jdbc:postgresql://keycloak-db:5432/keycloak` (hardcoded; internal infrastructure constant)
  - `KC_DB_USERNAME: ${KC_DB_USERNAME}`, `KC_DB_PASSWORD: ${KC_DB_PASSWORD}`
  - `KC_HOSTNAME_STRICT: "false"`

- **keycloak-db**: PostgreSQL 16 with named volume and healthcheck (`pg_isready`). Environment includes `POSTGRES_DB: keycloak` (hardcoded), `POSTGRES_USER: ${KC_DB_USERNAME}`, `POSTGRES_PASSWORD: ${KC_DB_PASSWORD}`.

- **keycloak-init**: Python one-shot container. Sets `KC_URL=http://keycloak:8080/auth` and `KC_ADMIN_USER`/`KC_ADMIN_PASSWORD` explicitly. Uses `restart: on-failure` as safety net only — the init container already has an internal wait loop (`KC_HEALTHCHECK_TIMEOUT`, default 300s). Seed file convention: mounts `./seed.yml:/app/seed.yml:ro` — users create their seed by copying `init/seeds/example.yml` to `seed.yml` at the repo root and editing it. No docker-compose edit required.

The `./seed.yml` path at repo root is the convention. `init/seeds/example.yml` remains as a reference template.

## .env.example

All variables needed to bring up the full stack. Variables hardcoded in docker-compose (e.g. `KC_DB=postgres`, internal DB URL, `KC_HOSTNAME_STRICT=false`) are not exposed — they are infrastructure constants, not user-facing configuration.

```env
# Keycloak admin credentials
KC_ADMIN_USER=admin
KC_ADMIN_PASSWORD=changeme

# Database credentials (used by both keycloak and keycloak-db services)
KC_DB_USERNAME=keycloak
KC_DB_PASSWORD=changeme

# Exposed port (default: 8080)
KC_PORT=8080

# How long (seconds) the init container waits for Keycloak to become ready (default: 300)
# KC_HEALTHCHECK_TIMEOUT=300

# Seed-specific variables (add yours here)
# APP_URL=http://localhost:3000
# SMTP_HOST=smtp.example.com
```

## README Sections

1. **Description** — generic kickstart intro
2. **Quickstart** — `cp .env.example .env` → edit → `cp init/seeds/example.yml seed.yml` → edit → `docker compose up`
3. **Seed file** — copy `init/seeds/example.yml` to `seed.yml` at the repo root, customize it, then run `docker compose up`. No docker-compose edit required — the volume mount is fixed to `./seed.yml`
4. **Custom theme** — link to official KC theme docs + instructions to re-add theme to `Dockerfile`
5. **Events & Webhooks** — description of included JAR provider and webhook configuration in seed

## Out of Scope

- Multiple seed examples / `examples/` directory (can be added later)
- docker-compose profiles for different environments
- Parameterized `KC_VERSION` build arg
- Changes to `keycloak-events/` directory (separate project)
