# Keycloak Kickstart Standardization — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform a client-specific Keycloak init repo into a reusable, context-agnostic kickstart template with docker-compose.

**Architecture:** Surgical cleanup — remove client artifacts, de-brand references, fix broken tests, add docker-compose stack (KC 26.1 + PostgreSQL 16 + Python init container). Python init logic is preserved; the only code-level changes are fixing stale test assertions and renaming client-branded strings.

**Tech Stack:** Docker, Docker Compose, Python 3.11, pytest, Keycloak 26.1, PostgreSQL 16

**Spec:** `docs/superpowers/specs/2026-03-18-keycloak-kickstart-standardization-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `init/tests/test_init.py` | Modify | Fix broken assertions, remove header comment |
| `init/tests/test_keycloak_client.py` | Modify | Replace `"builder"` with `"test-realm"`, remove stale `TestEnsureClientScope` class |
| `init/orchestrator.py` | Modify | Remove header comment, change default `KC_URL` |
| `init/seeds/example.yml` | Modify | Remove header comment, comment out `theme` line |
| `init/seeds/local.yml` | Delete | Client-specific seed |
| `init/Dockerfile` | Modify | Remove header comment |
| `Dockerfile` | Modify | KC 26.1, remove theme build stage |
| `themes/` | Delete | Client-specific theme assets |
| `.gitignore` | Create | Root gitignore |
| `.env.example` | Create | Documented environment variables |
| `docker-compose.yml` | Create | Full stack definition |
| `README.md` | Rewrite | Generic kickstart documentation |

---

### Task 1: Fix broken tests in `test_init.py`

**Files:**
- Modify: `init/tests/test_init.py`

The test `test_full_realm_setup` asserts calls to `ensure_client_scope` and `create_scope_mapper`, but these methods don't exist in `keycloak_client.py` or `orchestrator.py`. The test seed data also contains a `scope` key that `orchestrator.py` never reads. These assertions must be removed.

- [ ] **Step 1: Remove the broken assertions and stale seed data**

In `init/tests/test_init.py`, make these changes:

1. Remove line 1 (header comment `# rd-auth-server/init/tests/test_init.py`)
2. Remove line 30: `cfg.ensure_client_scope.return_value = "scope-uuid"`
3. Remove the `scope` key from the client dict in the test seed (line 42): `"scope": {"name": "role", "mapper": "client-role-mapper"},`
4. Remove the two broken assertions (lines 61-62):
   ```python
   cfg.ensure_client_scope.assert_called_once_with("test", "role")
   cfg.create_scope_mapper.assert_called_once()
   ```

The resulting `test_full_realm_setup` method should have the mock setup:
```python
cfg = MockCfg.return_value
cfg.ensure_client.return_value = "client-uuid"
cfg.ensure_group.return_value = "group-uuid"
cfg.ensure_user.return_value = "user-uuid"
```

And the seed client dict should be:
```python
{
    "clientId": "app",
    "app_url": "http://localhost",
    "roles": ["Admin"],
    "backchannel_logout_url": "http://api/logout",
    "disable_frontchannel_logout": True,
}
```

And the assertions should go directly from `ensure_role` to `ensure_group`:
```python
cfg.ensure_realm.assert_called_once_with("test")
cfg.ensure_client.assert_called_once()
cfg.ensure_role.assert_called_once_with("test", "client-uuid", "Admin")
cfg.ensure_group.assert_called_once_with("test", "devs")
cfg.ensure_user.assert_called_once()
cfg.assign_role_to_user.assert_called_once()
cfg.add_user_to_group.assert_called_once()
cfg.configure_smtp.assert_called_once()
cfg.configure_theme.assert_called_once_with("test", "custom")
cfg.configure_ssl.assert_called_once_with("test", "NONE")
cfg.configure_events.assert_called_once_with("test")
cfg.register_webhook.assert_called_once()
cfg.ensure_user_attribute.assert_called_once()
cfg.configure_backchannel_logout.assert_called_once()
cfg.disable_frontchannel_logout.assert_called_once()
cfg.reset_admin_password.assert_called_once_with("master", "admin", "newpass", temporary=False)
```

- [ ] **Step 2: Run tests to verify the fix**

Run: `cd /home/monte97/Projects/keycloak-kickstart/init && python -m pytest tests/test_init.py -v`
Expected: 2 tests PASS (test_full_realm_setup, test_minimal_realm_no_optional_sections)

- [ ] **Step 3: Commit**

```bash
git add init/tests/test_init.py
git commit -m "fix: remove broken assertions for non-existent ensure_client_scope/create_scope_mapper"
```

---

### Task 2: De-brand `test_keycloak_client.py` and remove stale `TestEnsureClientScope`

**Files:**
- Modify: `init/tests/test_keycloak_client.py`

The test file uses `"builder"` as realm name in every test (client-specific). It also contains `TestEnsureClientScope` (lines 118-131) that tests `ensure_client_scope` — a method that doesn't exist in `keycloak_client.py`.

- [ ] **Step 1: Replace `"builder"` with `"test-realm"` throughout and remove stale test class**

1. Replace all occurrences of `"builder"` with `"test-realm"` (appears on lines 24, 27, 32, 33, 42, 52, 61, 67, 76, 82, 92, 98, 107, 114, 123, 129, 139, 148, 157, 166, 187, 204, 212, 222)
2. Remove the entire `TestEnsureClientScope` class (lines 118-131):
   ```python
   class TestEnsureClientScope:
       def test_creates_scope_if_not_exists(self, configurator):
           ...
       def test_returns_existing_scope_id(self, configurator):
           ...
   ```

- [ ] **Step 2: Run tests to verify**

Run: `cd /home/monte97/Projects/keycloak-kickstart/init && python -m pytest tests/test_keycloak_client.py -v`
Expected: All tests PASS (the two removed tests no longer run; remaining tests pass with `"test-realm"`)

- [ ] **Step 3: Commit**

```bash
git add init/tests/test_keycloak_client.py
git commit -m "fix: de-brand test realm name and remove stale TestEnsureClientScope"
```

---

### Task 3: De-brand `orchestrator.py`

**Files:**
- Modify: `init/orchestrator.py`

Two changes: remove line 1 header comment, update default `KC_URL`.

- [ ] **Step 1: Remove header comment and update default KC_URL**

1. Remove line 1: `# rd-auth-server/init/orchestrator.py`
2. Change line 41 (after removal it becomes line 40):
   - From: `kc_url = os.environ.get("KC_URL", "http://rd-auth-server:8080/auth")`
   - To: `kc_url = os.environ.get("KC_URL", "http://keycloak:8080/auth")`

- [ ] **Step 2: Run all tests to verify nothing breaks**

Run: `cd /home/monte97/Projects/keycloak-kickstart/init && python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add init/orchestrator.py
git commit -m "fix: de-brand orchestrator header and default KC_URL"
```

---

### Task 4: Clean seed files and init/Dockerfile

**Files:**
- Modify: `init/seeds/example.yml`
- Delete: `init/seeds/local.yml`
- Modify: `init/Dockerfile`

- [ ] **Step 1: Clean `example.yml`**

1. Remove line 1: `# rd-auth-server/init/seeds/example.yml`
2. Replace line 14 (`    theme: custom-theme                         # optional`) with:
   ```yaml
   # theme: custom-theme                       # optional — requires adding theme to Dockerfile
   ```
   (Keep 4-space indent to match the surrounding YAML)

- [ ] **Step 2: Remove `local.yml`**

Delete: `init/seeds/local.yml`

- [ ] **Step 3: Clean `init/Dockerfile`**

Remove line 1: `# rd-auth-server/init/Dockerfile`

- [ ] **Step 4: Commit**

```bash
git add init/seeds/example.yml init/Dockerfile
git rm init/seeds/local.yml
git commit -m "chore: de-brand seed files and init Dockerfile, remove client-specific local.yml"
```

---

### Task 5: Update root Dockerfile to KC 26.1 and remove theme

**Files:**
- Modify: `Dockerfile`

- [ ] **Step 1: Update Dockerfile**

The new `Dockerfile` should be:

```dockerfile
FROM quay.io/keycloak/keycloak:26.1 as builder

WORKDIR /opt/keycloak

COPY ./provider/keycloak-events-26.0.jar /opt/keycloak/providers/

RUN /opt/keycloak/bin/kc.sh build

FROM quay.io/keycloak/keycloak:26.1

COPY --from=builder /opt/keycloak/ /opt/keycloak/

EXPOSE 8080

ENTRYPOINT ["/opt/keycloak/bin/kc.sh", "start"]
```

Changes from current:
- `26.0` → `26.1` (lines 2 and 18)
- Removed `ARG KC_THEME=default` (line 11)
- Removed `COPY ./themes/${KC_THEME}/ /opt/keycloak/themes/custom-theme/` (line 12)
- Removed comments (were generic, not needed)

- [ ] **Step 2: Commit**

```bash
git add Dockerfile
git commit -m "chore: update Keycloak to 26.1, remove theme from image"
```

---

### Task 6: Remove `themes/` directory

**Files:**
- Delete: `themes/` (entire directory)

- [ ] **Step 1: Remove themes directory**

```bash
git rm -r themes/
```

- [ ] **Step 2: Commit**

```bash
git commit -m "chore: remove client-specific theme directory"
```

---

### Task 7: Add root `.gitignore`

**Files:**
- Create: `.gitignore`

- [ ] **Step 1: Create `.gitignore`**

```gitignore
# Environment
.env
seed.yml

# Python
__pycache__/
*.pyc
.venv/
.pytest_cache/
```

- [ ] **Step 2: Commit**

```bash
git add .gitignore
git commit -m "chore: add root .gitignore"
```

---

### Task 8: Add `.env.example`

**Files:**
- Create: `.env.example`

- [ ] **Step 1: Create `.env.example`**

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

- [ ] **Step 2: Commit**

```bash
git add .env.example
git commit -m "chore: add .env.example with documented variables"
```

---

### Task 9: Add `docker-compose.yml`

**Files:**
- Create: `docker-compose.yml`

- [ ] **Step 1: Create `docker-compose.yml`**

```yaml
services:
  keycloak:
    build: .
    container_name: keycloak
    environment:
      KC_BOOTSTRAP_ADMIN_USERNAME: ${KC_ADMIN_USER:-admin}
      KC_BOOTSTRAP_ADMIN_PASSWORD: ${KC_ADMIN_PASSWORD}
      KC_DB: postgres
      KC_DB_URL: jdbc:postgresql://keycloak-db:5432/keycloak
      KC_DB_USERNAME: ${KC_DB_USERNAME}
      KC_DB_PASSWORD: ${KC_DB_PASSWORD}
      KC_HTTP_RELATIVE_PATH: /auth
      KC_HOSTNAME_STRICT: "false"
    ports:
      - "${KC_PORT:-8080}:8080"
    depends_on:
      keycloak-db:
        condition: service_healthy

  keycloak-db:
    image: postgres:16
    container_name: keycloak-db
    environment:
      POSTGRES_DB: keycloak
      POSTGRES_USER: ${KC_DB_USERNAME}
      POSTGRES_PASSWORD: ${KC_DB_PASSWORD}
    volumes:
      - keycloak-db-data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER}"]
      interval: 5s
      timeout: 5s
      retries: 10

  keycloak-init:
    build: ./init
    container_name: keycloak-init
    environment:
      KC_URL: http://keycloak:8080/auth
      KC_ADMIN_USER: ${KC_ADMIN_USER:-admin}
      KC_ADMIN_PASSWORD: ${KC_ADMIN_PASSWORD}
      KC_HEALTHCHECK_TIMEOUT: ${KC_HEALTHCHECK_TIMEOUT:-300}
      SEED_FILE: /app/seed.yml
    volumes:
      - ./seed.yml:/app/seed.yml:ro
    depends_on:
      - keycloak
    restart: on-failure

volumes:
  keycloak-db-data:
```

Note: `$${POSTGRES_USER}` in the healthcheck uses double `$` to escape Compose interpolation — the shell inside the container receives `${POSTGRES_USER}`.

- [ ] **Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add docker-compose with KC 26.1, PostgreSQL 16, and init container"
```

---

### Task 10: Rewrite `README.md`

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Rewrite README**

```markdown
# keycloak-kickstart

Opinionated Keycloak setup with automated realm initialization. Clone, configure, `docker compose up`.

## Quickstart

```bash
cp .env.example .env          # edit credentials
cp init/seeds/example.yml seed.yml  # edit realm/clients/users
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

The image includes `keycloak-events-26.0.jar`, a provider that enables webhook notifications for Keycloak events. Configure webhooks in your seed file:

```yaml
webhooks:
  - url: "http://your-service/webhook"
    events:
      - access.LOGIN
      - access.LOGOUT
      - admin.USER-DELETE
```

When webhooks are defined, the init container automatically enables event listeners and admin events for the realm.

## Architecture

| Service | Description |
|---|---|
| `keycloak` | Keycloak 26.1 with custom event provider |
| `keycloak-db` | PostgreSQL 16 for Keycloak storage |
| `keycloak-init` | Python one-shot container that configures realms from `seed.yml` |
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: rewrite README as generic kickstart documentation"
```

---

### Task 11: Final verification

- [ ] **Step 1: Run the full test suite**

Run: `cd /home/monte97/Projects/keycloak-kickstart/init && python -m pytest -v`
Expected: All tests PASS

- [ ] **Step 2: Verify no remaining `rd-auth-server` or `rd-builder` references**

Run: `grep -r "rd-auth-server\|rd-builder" /home/monte97/Projects/keycloak-kickstart/ --include="*.py" --include="*.yml" --include="*.md" --include="Dockerfile" --include="*.ftl" --include="*.css" --include="*.properties"`
Expected: No matches (themes/ is deleted, all headers cleaned)

- [ ] **Step 3: Verify no remaining `"builder"` as realm name in tests**

Run: `grep -rn '"builder"' /home/monte97/Projects/keycloak-kickstart/init/tests/`
Expected: No matches

- [ ] **Step 4: Verify file structure matches spec**

Run: `find /home/monte97/Projects/keycloak-kickstart -not -path '*/.venv/*' -not -path '*/__pycache__/*' -not -path '*/.pytest_cache/*' -not -path '*/.git/*' -not -path '*/.git' -not -path '*/keycloak-events/*' -not -path '*/docs/*' -not -path '*/.claude/*' -type f | sort`

Expected output should match the spec's repository structure.
