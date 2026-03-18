# rd-auth-server

Identity provider basato su Keycloak 26.0. Gestisce autenticazione OpenID Connect / OAuth2, realm, utenti, ruoli e client.

## Container

| Container | Scopo |
|---|---|
| `rd-auth-server` | Keycloak principale |
| `rd-auth-server-init` | Inizializzazione one-shot (crea realm, utenti, client, ruoli, webhook) |
| `rd-auth-db` | PostgreSQL dedicato a Keycloak |

## File

| File | Descrizione |
|---|---|
| `Dockerfile` | Immagine Keycloak con provider custom e tema |
| `Dockerfile.initializer` | Immagine Python per lo script di inizializzazione |
| `initKC_file.py` | Script che configura realm, utenti, client, ruoli, webhook, SMTP e tema |
| `requirements.txt` | Dipendenze Python (requests) |
| `provider/keycloak-events-26.0.jar` | Provider custom per eventi webhook |
| `themes/` | Temi login personalizzabili (selezionabile via parametro `kc_theme`) |

## Temi

I temi si trovano in `themes/<nome>/login/`. Il tema attivo e' configurabile con la variabile Ansible `kc_theme` (default: `default`).

Per aggiungere un nuovo tema, creare una sottocartella in `themes/` con la stessa struttura di `default/`.

## Porte

- `8080` interno (esposto come `9999` solo in modalita' infra)
- Accessibile esternamente via gateway su `/auth/`
