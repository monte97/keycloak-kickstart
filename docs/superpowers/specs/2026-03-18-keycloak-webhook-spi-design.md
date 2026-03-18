# Keycloak Webhook SPI Provider — Design Spec

**Date:** 2026-03-18
**Package:** `dev.montell.keycloak`
**Target:** Keycloak 26+, Java 17+, PostgreSQL
**Status:** Approved

---

## 1. Obiettivo

Riscrittura ex-novo del provider SPI Keycloak per la gestione dei webhook sugli eventi.
Il progetto di riferimento è `keycloak-events` (PhasTwo, `io.phasetwo.keycloak`).
Questa riscrittura risolve i problemi architetturali identificati, aggiunge circuit breaker,
retention policy, e una UI per la gestione dei webhook.

---

## 2. Struttura del repository

Progetto Maven a modulo singolo con package separation (come la reference), più
un sotto-progetto Node per la UI e un modulo test separato:

```
keycloak-webhook-provider/
├── pom.xml
├── src/main/java/dev/montell/keycloak/
│   ├── spi/                    ← WebhookSpi, WebhookProvider interface, WebhookProviderFactory
│   ├── model/                  ← WebhookModel, WebhookEventModel, WebhookSendModel, KeycloakEventType
│   ├── event/                  ← WebhookPayload (sealed interface), EventPatternMatcher, EventEnricher
│   ├── jpa/
│   │   ├── entity/             ← WebhookEntity, WebhookEventEntity, WebhookSendEntity
│   │   └── adapter/            ← WebhookAdapter, WebhookEventAdapter, WebhookSendAdapter
│   │   └── JpaWebhookProvider, JpaWebhookProviderFactory, WebhookEntityProvider[Factory]
│   ├── dispatch/               ← WebhookEventDispatcher, CircuitBreaker, CircuitBreakerRegistry
│   ├── sender/                 ← HttpWebhookSender, HmacSigner
│   ├── listener/               ← WebhookEventListenerProvider, WebhookEventListenerProviderFactory
│   ├── retention/              ← RetentionCleanupTask
│   └── resources/              ← WebhooksResource, WebhooksResourceProvider[Factory]
├── src/main/resources/
│   ├── META-INF/services/      ← generati da @AutoService
│   ├── META-INF/jpa-changelog-webhook.xml             ← master changelog Liquibase
│   ├── META-INF/jpa-changelog-webhook-1.0.0.xml       ← changeset iniziale
│   └── theme-resources/webhooks/                       ← UI build output (gitignored)
├── webhook-ui/                  ← sotto-progetto Node (React + PatternFly)
│   ├── package.json
│   ├── src/
│   └── dist/                    ← output build, copiato in theme-resources
└── src/test/
    ├── java/dev/montell/keycloak/
    │   ├── unit/                ← unit test puri (Mockito, no infra)
    │   └── it/                  ← integration test (Testcontainers)
    └── resources/
```

### Motivazione modulo singolo

Il JAR finale deployato in Keycloak è **uno solo**. Multi-module aggiungerebbe complessità
Maven (shade plugin `ServicesResourceTransformer`, inter-module version management) senza
benefici di deployment. La separazione per package garantisce la stessa testabilità.

---

## 3. SPI Registration e Keycloak Plumbing

### Provider SPI registrati

Tutte le Factory usano `@AutoService` (Google Auto-Service) che genera i file
`META-INF/services/*` a compile time.

| SPI | Factory | Provider ID |
|---|---|---|
| `Spi` (discovery) | — | `webhookProvider` (via `WebhookSpi`) |
| `WebhookProviderFactory` | `JpaWebhookProviderFactory` | `jpa-webhook` |
| `EventListenerProviderFactory` | `WebhookEventListenerProviderFactory` | `montell-webhook` |
| `JpaEntityProviderFactory` | `WebhookEntityProviderFactory` | `webhook-entity-provider` |
| `RealmResourceProviderFactory` | `WebhooksResourceProviderFactory` | `webhooks` |

### JPA Entity Registration

`WebhookEntityProviderFactory` implementa `JpaEntityProviderFactory` e restituisce
un `WebhookEntityProvider` (implementa `JpaEntityProvider`) con:

```java
@Override
public List<Class<?>> getEntities() {
    return List.of(
        WebhookEntity.class,
        WebhookEventEntity.class,
        WebhookSendEntity.class
    );
}

@Override
public String getChangelogLocation() {
    return "META-INF/jpa-changelog-webhook.xml";
}
```

Registrazione: `@AutoService(JpaEntityProviderFactory.class)`

### Liquibase Schema Migration

Il DDL viene gestito tramite Liquibase changelogs (non DDL manuale). Il master changelog
`META-INF/jpa-changelog-webhook.xml` include i changeset versionati:

```xml
<!-- jpa-changelog-webhook.xml -->
<databaseChangeLog>
    <include file="META-INF/jpa-changelog-webhook-1.0.0.xml"/>
</databaseChangeLog>
```

Il changeset `1.0.0` crea le tabelle iniziali (vedi schema §4).

### Realm Event Configuration

Per attivare il provider, il listener `montell-webhook` deve essere abilitato per-realm
in: Admin Console → Realm Settings → Events → Event Listeners → aggiungi `montell-webhook`.

Negli integration test, l'abilitazione avviene programmaticamente via Admin Client API:
```java
realmResource.update(RealmRepresentation.builder()
    .eventsListeners(List.of("montell-webhook"))
    .build());
```

### Fat JAR / Shade

Il `maven-shade-plugin` produce il JAR fat con `ServicesResourceTransformer` per
appendere (non sovrascrivere) i file `META-INF/services/*` da eventuali dipendenze:

```xml
<transformer implementation="org.apache.maven.plugins.shade.resource.ServicesResourceTransformer"/>
```

---

## 4. Modello dati

### Schema (via Liquibase changeset 1.0.0)

```sql
CREATE TABLE WEBHOOK (
    ID              VARCHAR(36)   PRIMARY KEY,
    REALM_ID        VARCHAR(255)  NOT NULL,
    URL             VARCHAR(2048) NOT NULL,
    SECRET          VARCHAR(255),          -- plaintext, vedi nota sicurezza §4.1
    ALGORITHM       VARCHAR(32)   NOT NULL DEFAULT 'HmacSHA256',
    ENABLED         BOOLEAN       NOT NULL DEFAULT FALSE,
    CIRCUIT_STATE   VARCHAR(16)   NOT NULL DEFAULT 'CLOSED',  -- CLOSED/OPEN/HALF_OPEN
    FAILURE_COUNT   INTEGER       NOT NULL DEFAULT 0,
    LAST_FAILURE_AT TIMESTAMP,
    CREATED_BY      VARCHAR(255),
    CREATED_AT      TIMESTAMP     NOT NULL,
    UPDATED_AT      TIMESTAMP     NOT NULL,
    RETRY_MAX_ELAPSED_SECONDS INTEGER,    -- null = usa default realm/globale
    RETRY_MAX_INTERVAL_SECONDS INTEGER
);

CREATE TABLE WEBHOOK_EVENT_TYPE (
    WEBHOOK_ID  VARCHAR(36)  NOT NULL REFERENCES WEBHOOK(ID) ON DELETE CASCADE,
    EVENT_TYPE  VARCHAR(255) NOT NULL,
    PRIMARY KEY (WEBHOOK_ID, EVENT_TYPE)
);

-- Audit trail degli eventi intercettati
-- EVENT_TYPE: discriminatore "USER" | "ADMIN" (non il tipo evento esteso)
-- EVENT_OBJECT: payload WebhookPayload serializzato come TEXT (portabile, no JSONB)
CREATE TABLE WEBHOOK_EVENT (
    ID           VARCHAR(36)  PRIMARY KEY,
    REALM_ID     VARCHAR(255) NOT NULL,
    EVENT_TYPE   VARCHAR(16)  NOT NULL,   -- "USER" o "ADMIN" (enum discriminatore)
    KC_EVENT_ID  VARCHAR(255),            -- ID evento Keycloak originale
    EVENT_OBJECT TEXT         NOT NULL,    -- JSON come TEXT (portabile cross-DB)
    CREATED_AT   TIMESTAMP    NOT NULL
);

CREATE INDEX webhook_event_realm_created_idx ON WEBHOOK_EVENT(REALM_ID, CREATED_AT);
CREATE UNIQUE INDEX webhook_event_kc_id_idx  ON WEBHOOK_EVENT(KC_EVENT_ID);
-- UNIQUE index su KC_EVENT_ID: garantisce idempotenza storeEvent() via constraint DB

-- SENT_AT: timestamp del primo tentativo di invio
-- LAST_ATTEMPT_AT: timestamp dell'ultimo tentativo
CREATE TABLE WEBHOOK_SEND (
    ID               VARCHAR(36)  PRIMARY KEY,
    WEBHOOK_ID       VARCHAR(36)  NOT NULL REFERENCES WEBHOOK(ID) ON DELETE CASCADE,
    WEBHOOK_EVENT_ID VARCHAR(36)  NOT NULL REFERENCES WEBHOOK_EVENT(ID) ON DELETE CASCADE,
    EVENT_TYPE       VARCHAR(255) NOT NULL,  -- tipo esteso es. "access.LOGIN"
    HTTP_STATUS      INTEGER,               -- HTTP status dell'ultimo tentativo
    RETRIES          INTEGER      NOT NULL DEFAULT 0,
    SUCCESS          BOOLEAN      NOT NULL DEFAULT FALSE,
    SENT_AT          TIMESTAMP    NOT NULL,
    LAST_ATTEMPT_AT  TIMESTAMP    NOT NULL,
    UNIQUE (WEBHOOK_ID, WEBHOOK_EVENT_ID)    -- idempotenza garantita da DB constraint
);

CREATE INDEX webhook_send_webhook_sent_idx ON WEBHOOK_SEND(WEBHOOK_ID, SENT_AT DESC);
CREATE INDEX webhook_send_event_idx        ON WEBHOOK_SEND(WEBHOOK_EVENT_ID);
```

### Retention policy (realm attributes)

| Attributo | Default | Descrizione |
|---|---|---|
| `_webhook.retention.events.days` | 30 | Giorni conservazione WEBHOOK_EVENT |
| `_webhook.retention.sends.days` | 90 | Giorni conservazione WEBHOOK_SEND |
| `_webhook.circuit.failure_threshold` | 5 | Fallimenti consecutivi per aprire il circuit |
| `_webhook.circuit.open_seconds` | 60 | Secondi prima di passare a HALF_OPEN |

### 4.1 Nota sicurezza — secret storage

Il campo `SECRET` è archiviato in plaintext su DB. Tradeoff consapevole in linea
con la reference implementation. Mitigazione: accesso al secret limitato al permesso
`manageEvents` (endpoint dedicato `GET /{id}/secret`).

Evoluzione futura: integrazione con `VaultProvider` di Keycloak.

---

## 5. Tassonomia eventi

Keycloak espone due stream distinti intercettati con metodi separati:

**`onEvent(Event event)`** — eventi utente, prefisso `access.`:
- `access.LOGIN`, `access.LOGIN_ERROR`, `access.LOGOUT`
- `access.REGISTER`
- `access.UPDATE_PASSWORD`, `access.UPDATE_PROFILE`, `access.UPDATE_EMAIL`
- `access.VERIFY_EMAIL`, `access.SEND_RESET_PASSWORD`, `access.RESET_PASSWORD`
- `access.DELETE_ACCOUNT`, `access.FEDERATED_IDENTITY_LINK`, `access.IMPERSONATE`
- (tutti i `EventType` Keycloak, prefissati con `access.`)

**`onEvent(AdminEvent event, boolean includeRepresentation)`** — operazioni admin, prefisso `admin.`:
- Formato: `admin.{ResourceType}-{OperationType}`
- Esempi: `admin.USER-CREATE`, `admin.USER-DELETE`, `admin.CLIENT_ROLE_MAPPING-CREATE`,
  `admin.GROUP_MEMBERSHIP-CREATE`, `admin.REALM-UPDATE`

### Nota

La registrazione di un nuovo utente genera due eventi separati:
- `access.REGISTER` — dal flusso utente
- `admin.USER-CREATE` — dal flusso admin

### Payload tipizzato

```java
record AuthDetails(String realmId, String clientId, String userId,
                   String username, String ipAddress) {}

sealed interface WebhookPayload permits WebhookPayload.AccessEvent, WebhookPayload.AdminEvent {

    record AccessEvent(
        String uid,
        String type,                   // "access.LOGIN"
        String realmId,
        String userId,
        String sessionId,
        Instant occurredAt,
        Map<String, String> details
    ) implements WebhookPayload {}

    record AdminEvent(
        String uid,
        String type,                   // "admin.USER-CREATE"
        String realmId,
        String resourcePath,
        OperationType operationType,
        AuthDetails authDetails,
        Instant occurredAt,
        JsonNode representation       // Jackson databind (provided via Keycloak runtime)
    ) implements WebhookPayload {}
}
```

### Pattern matching per eventTypes

| Pattern | Comportamento |
|---|---|
| `*` | Tutti gli eventi |
| `access.*` | Tutti gli eventi utente |
| `admin.*` | Tutti gli eventi admin |
| `access.LOGIN` | Exact match |
| `admin.USER-.*` | Regex |

Regex invalide: log WARNING esplicito con il pattern, il pattern viene ignorato.

---

## 6. Architettura dispatch

### Ownership e lifecycle

`WebhookEventDispatcher` è un **singleton** posseduto dal `WebhookEventListenerProviderFactory`.
La Factory (lifecycle: una per JVM) mantiene:
- `KeycloakSessionFactory factory` — per aprire nuove sessioni dai thread asincroni
- `ScheduledExecutorService executor` — pool di thread per invii asincroni + retry
- `CircuitBreakerRegistry circuitBreakers` — cache in-memory degli stati circuit breaker

`WebhookEventListenerProvider` (lifecycle: una per request) è stateless.

### Flusso

```
[Thread request Keycloak — sessione APERTA]

onEvent(Event/AdminEvent)
  │
  ▼
EventEnricher.enrich(event, session)    ← DEVE avvenire QUI, sessione ancora aperta
  │   aggiunge: username (da userId lookup), sessionId, userId
  ▼
RunnableTransaction.addRunnable(() → dispatcher.enqueue(enrichedPayload, realmId))

[Commit transazione Keycloak]

  ▼
RunnableTransaction.commitImpl()        ← ancora sul thread request
  │
  ▼
dispatcher.enqueue(payload, realmId)
  │   NOTA: enqueue() è NON-BLOCCANTE. Non fa operazioni DB.
  │   Sottomette un Runnable al ScheduledExecutorService:
  │   executor.submit(() → processAndSend(payload, realmId))
  │
  ▼
[Thread request completato — nessun blocco]

[Worker Thread — ScheduledExecutorService]

processAndSend(payload, realmId)
  │
  ▼
KeycloakModelUtils.runJobInTransaction(factory, session → {
  │   webhookProvider = session.getProvider(WebhookProvider.class)
  │   if (webhookProvider == null) { log.warn(...); return; }
  │   storeEvent(webhookProvider, payload)
  │     └─ try { persist } catch (ConstraintViolationException) { /* idempotente */ }
  │   webhooks = webhookProvider.getWebhooksStream(realm)
  │             .filter(enabled)
  │             .filter(w → EventPatternMatcher.matches(w.getEventTypes(), payload.type()))
  │             .toList()
  })
  │
  ▼
per ogni webhook:
  CircuitBreakerRegistry.get(webhookId).call()
    ├── OPEN      → skip, noop
    ├── HALF_OPEN → probe call
    │               success → CLOSED via runJobInTransaction
    │               fail    → OPEN via runJobInTransaction
    └── CLOSED    → HttpWebhookSender.send(url, payload, secret, algorithm)
                    [POST con timeout: connect 3s, read 10s]
                    [Header X-Keycloak-Signature: HMAC(payload, secret, algorithm)]
                    [Header X-Keycloak-Webhook-Id: {webhookId}]
                    │
                    ├── 2xx → runJobInTransaction(factory, session → {
                    │           storeSend(session, SUCCESS, httpStatus)
                    │           resetFailureCount(session, webhookId)
                    │         })
                    │
                    └── errore → runJobInTransaction(factory, session → {
                                   incrementFailureCount(session, webhookId)
                                   if (failureCount >= threshold) openCircuit(session, webhookId)
                                   storeSend(session, FAIL, httpStatus)
                                 })
                                 → se retryable: executor.schedule(retryTask, backoffDelay, MILLISECONDS)
```

### storeEvent() — idempotenza

L'idempotenza è garantita dal UNIQUE index su `KC_EVENT_ID`. Se un evento con lo stesso
`KC_EVENT_ID` esiste già, la `persist()` lancia `ConstraintViolationException` che viene
catturata silenziosamente (il record esiste, non serve duplicarlo).

### storeEvent() — errori DB

Se PostgreSQL non è disponibile, l'eccezione viene loggata come `ERROR` con il payload
serializzato. L'invio HTTP procede comunque (best-effort: webhook notificato ma audit
trail incompleto).

### Circuit breaker state machine

```
          failure >= threshold
CLOSED ──────────────────────▶ OPEN
  ▲                              │
  │                              │ after open_seconds
  │                   HALF_OPEN ◀┘
  │                      │
  │  probe success        │ probe fail
  └──────────────────────┘└──────▶ OPEN (reset timer)
```

Stato persistito su DB (`CIRCUIT_STATE`, `FAILURE_COUNT`, `LAST_FAILURE_AT`).
`CircuitBreakerRegistry` mantiene cache in memoria con TTL 5s.

**Nota cluster:** in deployment multi-nodo, ogni nodo ha la propria cache.
Comportamento **eventually consistent** (max 5s di divergenza).

### Semantica di delivery

**At-least-once delivery.** In un cluster multi-nodo, `onEvent()` può essere chiamato
su più nodi per lo stesso evento. Ogni nodo tenterà l'invio indipendentemente. Il UNIQUE
constraint su `WEBHOOK_SEND` previene la duplicazione del record DB, ma la POST HTTP
al consumer potrebbe arrivare più volte. I consumer devono essere idempotenti (tramite
il campo `uid` del payload).

### ScheduledExecutorService — dispatch e retry unificati

Non c'è una `BlockingQueue` separata. Il `ScheduledExecutorService` (dimensione pool:
`Runtime.availableProcessors()`) serve sia per il dispatch iniziale che per i retry
schedulati. Bounded submission logic:

```java
private final AtomicInteger pendingTasks = new AtomicInteger(0);
private static final int MAX_PENDING = 10_000;

void enqueue(WebhookPayload payload, String realmId) {
    if (pendingTasks.get() >= MAX_PENDING) {
        log.warn("Webhook dispatch queue full, dropping event: {}", payload.type());
        return;
    }
    pendingTasks.incrementAndGet();
    executor.submit(() -> {
        try {
            processAndSend(payload, realmId);
        } finally {
            pendingTasks.decrementAndGet();
        }
    });
}
```

### Graceful shutdown

`ProviderFactory.close()`:
- `executor.shutdown()`
- `executor.awaitTermination(30, SECONDS)`
- Task in attesa di retry con delay futuro vengono cancellati
- I record `WEBHOOK_SEND` con `SUCCESS=FALSE` rimangono come audit trail
- Non esiste logica di resume al riavvio (limitazione nota)

### ExponentialBackoff default

| Parametro | Default | Note |
|---|---|---|
| initialInterval | 500ms | |
| maxInterval | 180s | |
| maxElapsedTime | 900s | ~5-6 tentativi totali |
| multiplier | 5.0 | Sequenza: 500ms → 2.5s → 12.5s → 62.5s → 180s (cap) |
| randomizationFactor | 0.5 | |

Override per webhook: `RETRY_MAX_ELAPSED_SECONDS`, `RETRY_MAX_INTERVAL_SECONDS`.

---

## 7. RetentionCleanupTask

Schedulato tramite `TimerProvider` SPI. Il task implementa `ScheduledTask`:

```java
public class RetentionCleanupTask implements ScheduledTask {
    @Override
    public void run(KeycloakSession session) {
        // la session è già aperta in una transazione dal TimerProvider
        List<RealmModel> realms = session.realms().getRealmsStream().toList();
        for (RealmModel realm : realms) {
            int eventDays = getRetentionDays(realm, "_webhook.retention.events.days", 30);
            int sendDays  = getRetentionDays(realm, "_webhook.retention.sends.days", 90);

            EntityManager em = session.getProvider(JpaConnectionProvider.class).getEntityManager();
            em.createNativeQuery(
                "DELETE FROM WEBHOOK_EVENT WHERE REALM_ID = :realmId " +
                "AND CREATED_AT < CURRENT_TIMESTAMP - CAST(:days || ' days' AS INTERVAL)")
              .setParameter("realmId", realm.getId())
              .setParameter("days", eventDays)
              .executeUpdate();

            em.createNativeQuery(
                "DELETE FROM WEBHOOK_SEND ws WHERE ws.SENT_AT < CURRENT_TIMESTAMP " +
                "- CAST(:days || ' days' AS INTERVAL) " +
                "AND ws.WEBHOOK_ID IN (SELECT ID FROM WEBHOOK WHERE REALM_ID = :realmId)")
              .setParameter("realmId", realm.getId())
              .setParameter("days", sendDays)
              .executeUpdate();
        }
    }
}
```

Registrazione nel `postInit()` del `WebhookEventListenerProviderFactory`:

```java
@Override
public void postInit(KeycloakSessionFactory factory) {
    KeycloakModelUtils.runJobInTransaction(factory, session -> {
        TimerProvider timer = session.getProvider(TimerProvider.class);
        timer.scheduleTask(
            new RetentionCleanupTask(),
            TimeUnit.HOURS.toMillis(24),
            "montell-webhook-retention-cleanup"
        );
    });
}
```

**Nota:** la `session` passata a `run()` è già in transazione. Non è necessario
chiamare `runJobInTransaction()` all'interno del task.

**Nota portabilità:** la sintassi `CAST(:days || ' days' AS INTERVAL)` è
PostgreSQL-compatibile. Se in futuro si supportano altri DB, questi native query
andranno adattati.

---

## 8. REST API

**Base path:** `/realms/{realm}/webhooks` (no prefisso `/auth` — rimosso da Keycloak 17+)

Servito da `WebhooksResourceProvider` (implementa `RealmResourceProvider`) registrato
via `@AutoService(RealmResourceProviderFactory.class)`.

| Method | Path | Descrizione | Permesso |
|---|---|---|---|
| GET | `/` | Lista webhook (paginata: ?first&max) | viewEvents |
| POST | `/` | Crea webhook | manageEvents |
| GET | `/count` | Conta webhook | viewEvents |
| GET | `/{id}` | Dettaglio webhook (no secret) | viewEvents |
| PUT | `/{id}` | Aggiorna webhook | manageEvents |
| DELETE | `/{id}` | Elimina webhook | manageEvents |
| GET | `/{id}/secret` | Leggi secret | manageEvents |
| GET | `/{id}/events` | Log eventi ricevuti (?first&max) | viewEvents |
| GET | `/{id}/sends` | Log invii (?first&max&success=true\|false) | viewEvents |
| POST | `/{id}/sends/{sid}/resend` | Resend singolo | manageEvents |
| POST | `/{id}/resend-failed` | Resend bulk (?hours=24) | manageEvents |
| GET | `/{id}/circuit` | Stato circuit breaker | viewEvents |
| POST | `/{id}/circuit/reset` | Reset manuale → CLOSED | manageEvents |
| GET | `/events/{type}/{kid}` | Payload evento originale | viewEvents |
| GET | `/sends/{type}/{kid}` | Tutti gli invii per un evento | viewEvents |
| POST | `/test` | Invia evento di test (no persistenza) | manageEvents |

### Payload creazione webhook

```json
{
  "url": "https://my-app/hooks/keycloak",
  "secret": "my-secret",
  "algorithm": "HmacSHA256",
  "enabled": true,
  "eventTypes": ["access.LOGIN", "access.REGISTER", "admin.*"],
  "retryMaxElapsedSeconds": 300
}
```

### Payload test webhook

```json
{ "url": "https://...", "secret": "...", "algorithm": "HmacSHA256", "eventType": "access.LOGIN" }
```
Risposta: `{ "httpStatus": 200, "durationMs": 142, "success": true }`

---

## 9. UI — Webhooks Management

### Meccanismo di integrazione

La UI è servita tramite `RealmResourceProvider` (stesso provider della REST API).
Il frontend React (PatternFly) è bundlato nel JAR sotto `theme-resources/webhooks/`
e accessibile all'URL `/realms/{realm}/webhooks/ui`.

**Non si usa `UiTabProvider`** — non è una SPI pubblica stabile in Keycloak 26.
Il `RealmResourceProvider` è il meccanismo standard e provato per estendere Keycloak
con UI custom.

### Layout

Singola pagina con lista webhook espandibile:

```
Webhooks                                         [+ New Webhook]

┌─────────────────────────────────────────────────────────────┐
│ https://my-app/hooks/kc   ● CLOSED   ✓ enabled             │
│ access.LOGIN, access.REGISTER, admin.*                      │
│ [Send Log ▼]  [Test]  [Edit]  [Delete]                      │
└─────────────────────────────────────────────────────────────┘
┌─────────────────────────────────────────────────────────────┐
│ https://other/hook        ○ OPEN    ✗ disabled              │
│ admin.USER-DELETE                                           │
│ [Send Log ▼]  [Test]  [Edit]  [Reset CB]  [Delete]         │
└─────────────────────────────────────────────────────────────┘
```

### Componenti

- **Send Log** — accordion inline, ultimi 20 invii con status HTTP, retry count, resend per falliti
- **Test** — modal: seleziona event type, click, mostra status HTTP + durata
- **Edit** — modal: URL, secret, algorithm, event types (multi-select), enabled toggle, retry config
- **CircuitBreakerBadge** — ● CLOSED (verde) / ◐ HALF_OPEN (giallo) / ○ OPEN (rosso)
- **Reset CB** — visibile solo se circuit OPEN, resetta a CLOSED

### Build pipeline

```
webhook-ui/ (Node — frontend-maven-plugin scarica Node embedded)
  npm run build → dist/

maven-resources-plugin copia dist/ in:
  src/main/resources/theme-resources/webhooks/

maven-shade-plugin → fat JAR finale
```

---

## 10. Test suite

### Livelli

| Livello | Package | Tool | Infrastruttura |
|---|---|---|---|
| Unit | `dev.montell.keycloak.unit.*` | JUnit 5 + Mockito | nessuna |
| Component storage | `dev.montell.keycloak.it.storage.*` | JUnit 5 + Testcontainers | PostgreSQL (TC) |
| Component REST | `dev.montell.keycloak.unit.resources.*` | JUnit 5 + Mockito `@Mock KeycloakSession` | nessuna |
| Integration | `dev.montell.keycloak.it.*` | JUnit 5 + Testcontainers | Keycloak + PostgreSQL + WireMock (TC) |

Tutti i test sono standalone. I mock di `KeycloakSession` sono costruiti con Mockito.

### Unit test critici

```
CircuitBreakerTest
  ├── apre dopo N fallimenti consecutivi
  ├── non apre se fallimenti non consecutivi (reset al successo)
  ├── transisce a HALF_OPEN dopo open_seconds
  ├── chiude su probe success
  └── rimane OPEN su probe fail (reset timer)

WebhookEventDispatcherTest
  ├── enqueue → task sottomesso all'executor
  ├── non accoda per webhook disabilitati
  ├── non accoda se circuit OPEN
  ├── pendingTasks >= MAX_PENDING → log WARN, drop, nessuna eccezione
  └── enqueue() non blocca il thread chiamante

ExponentialBackOffTest
  ├── sequenza intervalli corretta
  ├── rispetta maxInterval
  └── si ferma dopo maxElapsedTime

HmacSignerTest
  ├── firma HmacSHA256 corretta (test vector noto)
  ├── firma HmacSHA1 corretta
  └── algoritmo non supportato → eccezione esplicita

EventPatternMatcherTest
  ├── "*" matcha tutto
  ├── "access.*" matcha solo eventi access
  ├── "admin.*" matcha solo eventi admin
  ├── exact match
  ├── regex valida matcha
  ├── regex invalida → log WARNING con pattern, no match, no eccezione
  └── event type null → no match

EventEnricherTest
  ├── aggiunge username da userId
  ├── aggiunge sessionId se presente
  └── userId null → nessuna eccezione, campo assente
```

### Component test storage (Testcontainers PostgreSQL)

```
JpaWebhookProviderTest
  ├── UNIQUE constraint su WEBHOOK_SEND previene duplicati
  ├── UNIQUE index su KC_EVENT_ID garantisce idempotenza storeEvent
  ├── CASCADE DELETE rimuove sends all'eliminazione webhook
  └── indici usati nelle query (EXPLAIN ANALYZE)

RetentionCleanupTaskTest
  ├── rimuove eventi più vecchi del threshold per realm
  ├── non rimuove eventi recenti
  ├── filtra WEBHOOK_SEND per realm via join su WEBHOOK
  └── usa default se realm attribute assente
```

### Integration test (Testcontainers: Keycloak + PostgreSQL + WireMock)

```
WebhookLifecycleIT
  ├── crea webhook via API, riceve LOGIN event, verifica payload HTTP su WireMock
  ├── crea webhook, riceve REGISTER event, verifica payload tipizzato AccessEvent
  ├── rollback transazione Keycloak NON triggera dispatch webhook
  ├── resend singolo di evento fallito
  └── resend bulk eventi falliti

CircuitBreakerIT
  ├── N fallimenti consecutivi → circuit OPEN → webhook non chiamato
  ├── dopo open_seconds → HALF_OPEN → probe call inviata
  ├── probe success → CLOSED → invii riprendono
  └── reset manuale via API → CLOSED immediato

WebhookSignatureIT
  └── consumer verifica HMAC-SHA256 su payload ricevuto: ricalcola HMAC e confronta header

SessionLifecycleIT
  ├── enrich() su thread request con sessione aperta (username risolto correttamente)
  └── worker thread apre sessione propria via runJobInTransaction (no NPE)

RealmConfigurationIT
  └── listener abilitato per realm → eventi intercettati; listener non abilitato → nessun invio
```

### Mutation testing (PIT)

```xml
<plugin>
  <groupId>org.pitest</groupId>
  <artifactId>pitest-maven</artifactId>
  <configuration>
    <targetClasses>
      <param>dev.montell.keycloak.dispatch.*</param>
      <param>dev.montell.keycloak.sender.*</param>
      <param>dev.montell.keycloak.event.*</param>
    </targetClasses>
    <mutators>STRONGER</mutators>
    <mutationThreshold>80</mutationThreshold>
    <coverageThreshold>85</coverageThreshold>
  </configuration>
</plugin>
```

---

## 11. Limitazioni note e decisioni consapevoli

| Limitazione | Decisione |
|---|---|
| Retry in-flight persi al shutdown | Accettato: WEBHOOK_SEND con SUCCESS=FALSE come audit. No resume al riavvio. |
| At-least-once delivery in cluster | Accettato: consumer devono essere idempotenti via `uid` |
| Circuit breaker eventually consistent | Accettato: TTL 5s cache, stato DB è fonte di verità |
| Secret in plaintext su DB | Accettato: VaultProvider come evoluzione futura |
| Secret in memoria nel pending task | Accettato: stesso rischio di qualsiasi in-process credential handling |
| Retention SQL PostgreSQL-specific | Accettato: target dichiarato è PostgreSQL. Adattamento necessario per altri DB |
| SSE live feed escluso | Rimandato: la UI usa polling ogni 10s |

---

## 12. Miglioramenti rispetto alla reference

| Problema reference | Soluzione |
|---|---|
| `synchronized` su `storeEvent()` e `afterSend()` | Rimossi: idempotenza via UNIQUE constraint DB + catch `ConstraintViolationException` |
| Nessun indice su WEBHOOK_SEND | 2 indici aggiunti |
| Nessun circuit breaker | `CircuitBreakerRegistry` con stato persistito su DB |
| Race condition in `storeSend()` | UNIQUE constraint DB |
| JSON cloning via serializzazione | Payload immutabile (`record`), nessun clone |
| Regex invalide ingoiate silenziosamente | Log WARNING esplicito |
| Nessun timeout su HTTP client | connect 3s, read 10s |
| Nessuna retention policy | `RetentionCleanupTask` via `TimerProvider`, configurabile per realm |
| Secret in GET response | Endpoint dedicato `/secret` con permesso `manageEvents` |
| Payload unificato Event+AdminEvent | `sealed interface WebhookPayload` con `permits` |
| `dispatch()` blocca thread request | `enqueue()` non-bloccante, DB operations su worker thread |
| Nessuna UI | React + PatternFly servita da `RealmResourceProvider` |
| Schema migration manuale | Liquibase changelogs via `JpaEntityProvider` |
