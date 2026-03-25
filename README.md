# keycloak-kickstart

> Opinionated Keycloak setup with automated realm initialization. Clone, configure, `docker compose up`.

[![License](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![CI](https://github.com/monte97/keycloak-kickstart/actions/workflows/ci.yml/badge.svg)](https://github.com/monte97/keycloak-kickstart/actions/workflows/ci.yml)

## Quickstart

```bash
cp .env.example .env                    # edit credentials
cp init/seeds/example.yml seed.yml      # edit realm/clients/users
docker compose up
```

Keycloak will be available at `http://localhost:8080/auth` (or the port set in `.env`).

## What's Inside

- **Keycloak 26.1** with [keycloak-webhook-provider](https://github.com/monte97/keycloak-webhook-provider) pre-installed
- **PostgreSQL 18** for persistent storage
- **Python init container** that configures realms, clients, users, roles, groups, webhooks from a single YAML file
- **Idempotent** — re-running is safe, only applies the delta

## Seed File

The init container reads `seed.yml` to configure Keycloak on first boot. Copy `init/seeds/example.yml` and customize it.

Environment variable interpolation:

- `${VAR}` — required, error if missing
- `${VAR:-default}` — optional, uses default if missing

See `init/seeds/example.yml` for all supported fields: realms, clients, roles, groups, users, SMTP, webhooks (with secret, algorithm, retry config), user attributes, logout configuration, and admin password reset.

## Integrating Your Application

### React / JavaScript SPA

```javascript
import Keycloak from 'keycloak-js';

const kc = new Keycloak({
  url: 'http://localhost:8080/auth',
  realm: 'my-realm',         // from your seed.yml
  clientId: 'my-app',        // from your seed.yml
});

await kc.init({ onLoad: 'check-sso', pkceMethod: 'S256' });

// Use kc.token in API calls
fetch('/api/data', {
  headers: { Authorization: `Bearer ${kc.token}` },
});
```

See [keycloak-js docs](https://www.keycloak.org/securing-apps/javascript-adapter) for full reference.

### Node.js / Express (API)

```javascript
const { createRemoteJWKSet, jwtVerify } = require('jose');

const JWKS = createRemoteJWKSet(
  new URL('http://localhost:8080/auth/realms/my-realm/protocol/openid-connect/certs')
);

async function requireAuth(req, res, next) {
  const token = req.headers.authorization?.replace('Bearer ', '');
  if (!token) return res.status(401).json({ error: 'No token' });

  try {
    const { payload } = await jwtVerify(token, JWKS, {
      issuer: 'http://localhost:8080/auth/realms/my-realm',
    });
    req.user = payload;
    next();
  } catch {
    res.status(401).json({ error: 'Invalid token' });
  }
}
```

### .NET

```csharp
// Program.cs
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.Authority = "http://localhost:8080/auth/realms/my-realm";
        options.Audience = "my-app";
        options.RequireHttpsMetadata = false; // dev only
    });
```

### Go

```go
import "github.com/coreos/go-oidc/v3/oidc"

provider, _ := oidc.NewProvider(ctx,
    "http://localhost:8080/auth/realms/my-realm")

verifier := provider.Verifier(&oidc.Config{ClientID: "my-app"})

// In handler:
token, err := verifier.Verify(ctx, rawToken)
```

### Python (FastAPI)

```python
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
import httpx, jose.jwt

JWKS_URL = "http://localhost:8080/auth/realms/my-realm/protocol/openid-connect/certs"
ISSUER = "http://localhost:8080/auth/realms/my-realm"

async def get_current_user(token=Depends(HTTPBearer())):
    jwks = httpx.get(JWKS_URL).json()
    try:
        return jose.jwt.decode(token.credentials, jwks, issuer=ISSUER)
    except jose.JWTError:
        raise HTTPException(401)
```

> **Note:** Replace `http://localhost:8080/auth` with your Keycloak URL. In Docker networks, use the internal URL (`http://keycloak:8080/auth`) for JWKS retrieval and the public URL for issuer validation.

## Events & Webhooks

Configure webhooks in your seed file:

```yaml
webhooks:
  - url: "http://your-service/webhook"
    secret: "${WEBHOOK_SECRET}"           # HMAC signing
    events:
      - access.LOGIN
      - access.LOGOUT
      - admin.USER-DELETE
```

- **Admin UI:** `http://localhost:8080/auth/realms/{realm}/webhooks/ui`
- **REST API:** `http://localhost:8080/auth/realms/{realm}/webhooks`

See [keycloak-webhook-provider](https://github.com/monte97/keycloak-webhook-provider) for full API reference.

## Custom Theme

1. Create your theme under `themes/<name>/login/`
2. Add to `Dockerfile` before the `RUN` build step:
   ```dockerfile
   COPY ./themes/<name>/ /opt/keycloak/themes/<name>/
   ```
3. Set `theme: <name>` in your `seed.yml`

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
make logs     Tail all logs
make health   Check Keycloak + DB + init status
make test     Run init container unit tests
make clean    Stop and remove volumes (full reset)
```

## Blog Posts

- [Keycloak: Cos'è e Perché Usarlo](https://montelli.dev/blog/progettare/keycloak/01-keycloak-intro/)
- [Authorization Code + PKCE](https://montelli.dev/blog/progettare/keycloak/02-authorization-code-pkce/)
- [M2M: Client Credentials](https://montelli.dev/blog/progettare/keycloak/03-keycloak-m2m/)
- [6 Problemi Reali](https://montelli.dev/blog/progettare/keycloak/04-keycloak-e2e/)
- [OPA + Keycloak](https://montelli.dev/blog/progettare/keycloak/05-keycloak-opa/)
- [Federation](https://montelli.dev/blog/progettare/keycloak/06-keycloak-federation/)

## Commercial Support

Need Keycloak configured for your team? I offer a productized **Keycloak SSO Setup** service with fixed scope, transparent pricing, and training included.

**What you get beyond this repo:**
- Integration with your application(s) — not a template, your actual code
- Reverse proxy (Traefik/Nginx) with HTTPS and Let's Encrypt
- Security hardening (brute force protection, session management, CORS)
- MFA, federation with your identity provider (Google/Azure AD/LDAP)
- Operational runbook (backup, restore, upgrade procedures)
- Hands-on workshop with your team (3–6 hours)

This repo is the "do it yourself" version. The service includes personalization, integration with your stack, team workshop, and ongoing support.

→ **[View services and pricing](https://montelli.dev/servizi/keycloak)**
→ **[Book a free 15-min call](https://calendly.com/montelli)**

## License

[MIT License](LICENSE) — Copyright (c) 2026 Francesco Montelli
