"""Keycloak init orchestrator — reads seed, configures KC idempotently."""

import logging
import os
import sys
import time

import requests as http_requests

from keycloak_client import KeycloakConfigurator
from seed_loader import load_seed

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def wait_for_keycloak(url: str, timeout: int = 300) -> None:
    """Wait until KC /realms/master returns 200."""
    endpoint = f"{url}/realms/master"
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = http_requests.get(endpoint, verify=False, timeout=5)
            if resp.status_code == 200:
                logger.info("Keycloak is ready at %s", url)
                return
        except http_requests.RequestException:
            pass
        logger.info("Waiting for Keycloak at %s ...", endpoint)
        time.sleep(5)
    logger.error("Keycloak not ready after %ds", timeout)
    sys.exit(1)


def main() -> None:
    seed_file = os.environ.get("SEED_FILE", "/app/seed.yml")
    kc_url = os.environ.get("KC_URL", "http://keycloak:8080/auth")
    kc_admin_user = os.environ.get("KC_ADMIN_USER", "admin")
    kc_admin_password = os.environ.get("KC_ADMIN_PASSWORD")
    kc_timeout = int(os.environ.get("KC_HEALTHCHECK_TIMEOUT", "300"))

    if not kc_admin_password:
        logger.error("KC_ADMIN_PASSWORD is required")
        sys.exit(1)

    seed = load_seed(seed_file)
    wait_for_keycloak(kc_url, timeout=kc_timeout)

    cfg = KeycloakConfigurator(
        server_url=kc_url,
        admin_user=kc_admin_user,
        admin_password=kc_admin_password,
    )

    for realm in seed["realms"]:
        realm_name = realm["name"]
        logger.info("=== Configuring realm '%s' ===", realm_name)

        # 1. Realm
        cfg.ensure_realm(realm_name)

        # 1b. SSL
        if "ssl_required" in realm:
            cfg.configure_ssl(realm_name, realm["ssl_required"])

        # 2. Clients + roles
        client_uuids = {}
        for client in realm.get("clients", []):
            client_id = client["clientId"]
            client_uuid = cfg.ensure_client(
                realm_name, client_id,
                app_url=client.get("app_url", ""),
                public_client=client.get("public_client", True),
                direct_access_grants=client.get("direct_access_grants", True),
            )
            client_uuids[client_id] = client_uuid
            for role in client.get("roles", []):
                cfg.ensure_role(realm_name, client_uuid, role)

        # 3. Groups
        group_uuids = {}
        for group in realm.get("groups", []):
            group_uuids[group["name"]] = cfg.ensure_group(realm_name, group["name"])

        # 5. Users + assignments
        for user in realm.get("users", []):
            user_id = cfg.ensure_user(
                realm_name, user["username"], user["password"],
                temporary=user.get("temporary", False),
            )
            for role in user.get("roles", []):
                # Find which client owns this role
                for client in realm["clients"]:
                    if role in client.get("roles", []):
                        cfg.assign_role_to_user(
                            realm_name, user_id,
                            client_uuids[client["clientId"]], role,
                        )
                        break
            for group_name in user.get("groups", []):
                cfg.add_user_to_group(realm_name, user_id, group_uuids[group_name])

        # 6. SMTP
        if "smtp" in realm:
            cfg.configure_smtp(realm_name, realm["smtp"])

        # 7. Theme
        if "theme" in realm:
            cfg.configure_theme(realm_name, realm["theme"])

        # 8. Events (must be before webhooks)
        if realm.get("webhooks"):
            cfg.configure_events(realm_name)

        # 9. Webhooks
        for wh in realm.get("webhooks", []):
            cfg.register_webhook(realm_name, wh)

        # 10. User attributes
        for attr in realm.get("user_attributes", []):
            cfg.ensure_user_attribute(realm_name, attr)

        # 11. Logout config (per client)
        for client in realm.get("clients", []):
            client_uuid = client_uuids[client["clientId"]]
            if "backchannel_logout_url" in client:
                cfg.configure_backchannel_logout(
                    realm_name, client_uuid, client["backchannel_logout_url"],
                )
            if client.get("disable_frontchannel_logout"):
                cfg.disable_frontchannel_logout(realm_name, client_uuid)

        # 12. Admin password reset
        admin_config = realm.get("admin")
        if admin_config and "reset_password" in admin_config:
            cfg.reset_admin_password(
                "master", kc_admin_user,
                admin_config["reset_password"],
                temporary=admin_config.get("temporary", False),
            )

        logger.info("=== Realm '%s' configured successfully ===", realm_name)


if __name__ == "__main__":
    main()
