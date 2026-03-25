# Keycloak Webhook Provider — Stato del Progetto

**Ultimo aggiornamento:** 2026-03-25

---

## Riepilogo

Provider SPI custom per Keycloak 26 che intercetta eventi (user e admin), li invia come webhook HTTP con firma HMAC, retry esponenziale e circuit breaker. Include REST API completa per gestione, monitoraggio e resend.

---

## Piani completati

### Piano 1: Foundation (8 commit)
- SPI interfaces e domain models (`WebhookModel`, `WebhookEventModel`, `WebhookSendModel`)
- Tassonomia eventi (`KeycloakEventType`, `EventPatternMatcher`, `WebhookPayload`)
- JPA entities con Liquibase changelog, adapters, `JpaWebhookProvider`
- Integration test con Testcontainers PostgreSQL

### Piano 2: Dispatch (14 commit)
- `HmacSigner` (HmacSHA256/HmacSHA1)
- `HttpWebhookSender` con timeout (connect 3s, read 10s) e firma
- `ExponentialBackOff` con jitter
- `CircuitBreaker` state machine (CLOSED/OPEN/HALF_OPEN) + `CircuitBreakerRegistry` con TTL cache
- `EventEnricher` (arricchisce eventi KC → `WebhookPayload`)
- `WebhookEventDispatcher` (coda asincrona, retry, circuit breaker)
- `WebhookEventListenerProvider` + Factory (enqueue on commit)
- `RetentionCleanupTask` (pulizia eventi/invii vecchi)
- REST CRUD endpoints per webhook management
- PITest mutation testing configurato

### Piano 3: REST API Extended (6 commit)
- `WebhookComponentHolder` (singleton sharing cross-provider)
- GET /{id}/events, GET /{id}/sends (paginati, filtro success)
- GET /{id}/circuit, POST /{id}/circuit/reset
- POST /{id}/test (ping, no persistence, no CB)
- POST /{id}/sends/{sid}/resend (Svix-style, rispetta CB)
- POST /{id}/resend-failed (bulk, stop al primo fallimento)
- 18 unit test per i nuovi endpoint

### Auth Granulare + Lookup Endpoints (3 commit)
- Auth migrata da "realm admin only" a `AdminPermissionEvaluator` (lazy init)
  - `requireViewEvents()` → `permissions.realm().requireViewEvents()`
  - `requireManageEvents()` → `permissions.realm().requireManageEvents()`
- GET /events/{type}/{kid} — lookup evento per KC event type + ID
- GET /sends/{type}/{kid} — lookup invii per KC event type + ID
- 8 unit test per i lookup endpoint
- Refactoring: `toEventMap()`/`toSendMap()` helpers, fix `initAuth()` ordering

---

## Stato attuale

| Metrica | Valore |
|---|---|
| Commit totali | ~66 |
| File Java (src/main) | 36 |
| File test | 9 (Java) + 4 (JS) |
| Test totali | 82 (Java unit) + 7 (IT) + 24 (JS) = 113 |
| Unit test passanti | 82/82 (Java) + 24/24 (JS) |
| Endpoint REST | 16 + 2 (UI serve) |
| Named queries JPA | 7 |
| Keycloak version | 26.0.0 |
| Java version | 17 |
| Admin UI | React + PatternFly 5.4, bundled nel JAR |

### Endpoint REST completi

| Method | Path | Permesso | Status |
|---|---|---|---|
| GET | `/` | viewEvents | ✅ |
| GET | `/count` | viewEvents | ✅ |
| GET | `/{id}` | viewEvents | ✅ |
| POST | `/` | manageEvents | ✅ |
| PUT | `/{id}` | manageEvents | ✅ |
| DELETE | `/{id}` | manageEvents | ✅ |
| GET | `/{id}/secret` | manageEvents | ✅ |
| GET | `/{id}/events` | viewEvents | ✅ |
| GET | `/{id}/sends` | viewEvents | ✅ |
| GET | `/{id}/circuit` | viewEvents | ✅ |
| POST | `/{id}/circuit/reset` | manageEvents | ✅ |
| POST | `/{id}/test` | manageEvents | ✅ |
| POST | `/{id}/sends/{sid}/resend` | manageEvents | ✅ |
| POST | `/{id}/resend-failed` | manageEvents | ✅ |
| GET | `/events/{type}/{kid}` | viewEvents | ✅ |
| GET | `/sends/{type}/{kid}` | viewEvents | ✅ |

---

### Piano 4: Admin UI React + PatternFly (24 commit)
- Submodulo `webhook-ui/` con Vite 5 + React 18 + TypeScript 5 + PatternFly 5.4
- Build via `frontend-maven-plugin` 1.15.1 (Node 20 embedded, npm ci/test/build)
- Bundled nel JAR sotto `webhook-ui/` — servita da endpoint JAX-RS
- `GET /realms/{realm}/webhooks/ui` — serve `index.html` con `{{REALM}}`/`{{BASE_PATH}}` sostituiti server-side
- `GET /realms/{realm}/webhooks/ui/{path}` — serve asset statici con cache headers
- Componenti: `WebhookTable`, `WebhookModal`, `CircuitBadge`, `ErrorBoundary`
- 24 test (Vitest + React Testing Library): WebhookTable, WebhookModal, CircuitBadge, ErrorBoundary
- Security: path traversal check, XSS-safe error handler, Content-Type header solo con body

## Lavoro rimanente

### 2. Integration Tests — medio
Da spec (sezione 10):
- Testcontainers con Keycloak + PostgreSQL + WireMock
- Test end-to-end: webhook lifecycle, circuit breaker, HMAC signature verification, session lifecycle, realm configuration
- Setup complesso, piano dedicato

### 3. Miglioramenti futuri (non pianificati)
- SSE live feed per eventi in tempo reale (escluso dalla spec, polling ogni 10s)
- Encryption at rest per i secret
- PostgreSQL-agnostic retention SQL

---

## Struttura progetto

```
keycloak-webhook-provider/
├── pom.xml
└── src/
    ├── main/java/dev/montell/keycloak/
    │   ├── spi/           — WebhookSpi, WebhookProvider, WebhookProviderFactory
    │   ├── model/         — WebhookModel, WebhookEventModel, WebhookSendModel, KeycloakEventType
    │   ├── event/         — EventEnricher, EventPatternMatcher, WebhookPayload, AuthDetails
    │   ├── jpa/           — JpaWebhookProvider, entities, adapters
    │   ├── dispatch/      — WebhookEventDispatcher, CircuitBreaker, ExponentialBackOff, WebhookComponentHolder
    │   ├── sender/        — HttpWebhookSender, HmacSigner, HttpSendResult
    │   ├── listener/      — WebhookEventListenerProvider, Factory
    │   ├── retention/     — RetentionCleanupTask
    │   └── resources/     — WebhooksResource, WebhookRepresentation, ResourceProvider
    ├── main/resources/    — Liquibase changelog, META-INF services
    └── test/java/dev/montell/keycloak/
        ├── unit/          — 8 unit test classes (82 test)
        └── it/            — 1 integration test class (7 test)
```

---

## Documentazione

| Tipo | Path |
|---|---|
| Spec principale | `docs/superpowers/specs/2026-03-18-keycloak-webhook-spi-design.md` |
| Spec REST API (Piano 3) | `docs/superpowers/specs/2026-03-19-webhook-rest-api-design.md` |
| Spec Auth + Lookup | `docs/superpowers/specs/2026-03-19-webhook-auth-and-lookup-endpoints-design.md` |
| Piano 1: Foundation | `docs/superpowers/plans/2026-03-18-webhook-provider-plan1-foundation.md` |
| Piano 2: Dispatch | `docs/superpowers/plans/2026-03-18-webhook-provider-plan2-dispatch.md` |
| Piano 3: REST API | `docs/superpowers/plans/2026-03-19-webhook-provider-plan3-rest-api.md` |
| Piano Auth + Lookup | `docs/superpowers/plans/2026-03-19-webhook-auth-and-lookup-plan.md` |

---

## Note operative

- **Java 17 richiesto**: SDKMAN è configurato su Java 11 di default. Usare `sdk use java 17.0.0-tem` o settare `JAVA_HOME=~/.sdkman/candidates/java/17.0.0-tem`
- **AdminPermissionEvaluator**: il package in Keycloak 26 è `org.keycloak.services.resources.admin.permissions` (non `fgap` come nel modulo keycloak-events)
- **Test IT**: richiedono Docker per Testcontainers (`mvn verify` per eseguirli)
- **PITest**: `mvn org.pitest:pitest-maven:mutationCoverage` (solo unit test)
