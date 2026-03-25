"""Idempotent Keycloak configuration wrapper over python-keycloak."""

import logging

import requests
from keycloak import KeycloakAdmin

logger = logging.getLogger(__name__)


class KeycloakConfigurator:
    def __init__(self, server_url: str, admin_user: str, admin_password: str):
        # Ensure trailing slash — python-keycloak uses urljoin which drops
        # the last path segment without it (e.g. /auth -> /)
        if not server_url.endswith("/"):
            server_url = server_url + "/"
        self._server_url = server_url
        self._admin_user = admin_user
        self._admin_password = admin_password
        self._admin = KeycloakAdmin(
            server_url=server_url,
            username=admin_user,
            password=admin_password,
            realm_name="master",
            verify=False,
        )

    def _switch_realm(self, realm_name: str) -> None:
        self._admin.realm_name = realm_name

    def ensure_realm(self, name: str, **config) -> None:
        existing = [r["realm"] for r in self._admin.get_realms()]
        if name in existing:
            logger.info("Realm '%s' already exists, skipping", name)
            return
        payload = {"realm": name, "enabled": True, "rememberMe": True}
        payload.update(config)
        self._admin.create_realm(payload)
        logger.info("Created realm '%s'", name)

    def ensure_client(self, realm: str, client_id: str, app_url: str = "",
                      public_client: bool = True, direct_access_grants: bool = True,
                      **kwargs) -> str:
        self._switch_realm(realm)
        existing = self._admin.get_clients()
        for c in existing:
            if c["clientId"] == client_id:
                logger.info("Client '%s' already exists in realm '%s'", client_id, realm)
                return c["id"]
        payload = {
            "clientId": client_id,
            "enabled": True,
            "publicClient": public_client,
            "directAccessGrantsEnabled": direct_access_grants,
            "redirectUris": [f"{app_url}/*"] if app_url else [],
            "baseUrl": app_url,
            "rootUrl": app_url,
            "webOrigins": [app_url] if app_url else [],
        }
        result = self._admin.create_client(payload)
        logger.info("Created client '%s' in realm '%s'", client_id, realm)
        return result

    def ensure_role(self, realm: str, client_uuid: str, role_name: str) -> None:
        self._switch_realm(realm)
        existing = self._admin.get_client_roles(client_uuid)
        if any(r["name"] == role_name for r in existing):
            logger.info("Role '%s' already exists, skipping", role_name)
            return
        self._admin.create_client_role(client_uuid, {"name": role_name})
        logger.info("Created role '%s'", role_name)

    def ensure_group(self, realm: str, group_name: str) -> str:
        self._switch_realm(realm)
        existing = self._admin.get_groups()
        for g in existing:
            if g["name"] == group_name:
                logger.info("Group '%s' already exists in realm '%s'", group_name, realm)
                return g["id"]
        result = self._admin.create_group({"name": group_name})
        logger.info("Created group '%s' in realm '%s'", group_name, realm)
        return result

    def ensure_user(self, realm: str, username: str, password: str,
                    temporary: bool = False) -> str:
        self._switch_realm(realm)
        existing = self._admin.get_users(query={"username": username, "exact": True})
        for u in existing:
            if u["username"] == username:
                logger.info("User '%s' already exists in realm '%s'", username, realm)
                return u["id"]
        user_id = self._admin.create_user({
            "username": username,
            "enabled": True,
            "credentials": [{"type": "password", "value": password, "temporary": temporary}],
        })
        logger.info("Created user '%s' in realm '%s'", username, realm)
        return user_id

    def assign_role_to_user(self, realm: str, user_id: str, client_uuid: str,
                            role_name: str) -> None:
        self._switch_realm(realm)
        role = self._admin.get_client_role(client_uuid, role_name)
        self._admin.assign_client_role(user_id=user_id, client_id=client_uuid, roles=[role])
        logger.info("Assigned role '%s' to user '%s'", role_name, user_id)

    def add_user_to_group(self, realm: str, user_id: str, group_id: str) -> None:
        self._switch_realm(realm)
        self._admin.group_user_add(user_id, group_id)
        logger.info("Added user '%s' to group '%s'", user_id, group_id)

    def configure_smtp(self, realm: str, smtp_config: dict) -> None:
        self._switch_realm(realm)
        self._admin.update_realm(realm, payload={
            "smtpServer": {
                "host": smtp_config["host"],
                "port": str(smtp_config["port"]),
                "from": smtp_config["sender"],
                "user": smtp_config.get("username", ""),
                "password": smtp_config.get("password", ""),
                "auth": "true" if smtp_config.get("username") else "false",
                "ssl": "true" if smtp_config.get("ssl") else "false",
                "starttls": "true" if smtp_config.get("starttls") else "false",
            }
        })
        logger.info("Configured SMTP for realm '%s'", realm)

    def configure_theme(self, realm: str, theme_name: str) -> None:
        self._switch_realm(realm)
        self._admin.update_realm(realm, payload={"loginTheme": theme_name})
        logger.info("Set login theme '%s' for realm '%s'", theme_name, realm)

    def configure_ssl(self, realm: str, ssl_required: str) -> None:
        self._switch_realm(realm)
        self._admin.update_realm(realm, payload={"sslRequired": ssl_required})
        logger.info("Set sslRequired='%s' for realm '%s'", ssl_required, realm)

    def configure_events(self, realm: str) -> None:
        self._switch_realm(realm)
        self._admin.update_realm(realm, payload={
            "eventsListeners": ["jboss-logging", "ext-event-webhook"],
            "eventsEnabled": "true",
            "adminEventsEnabled": "true",
            "adminEventsDetailsEnabled": "true",
            "enabledEventTypes": [
                "LOGIN", "LOGIN_ERROR", "REGISTER", "REGISTER_ERROR",
                "LOGOUT", "LOGOUT_ERROR", "CODE_TO_TOKEN", "CODE_TO_TOKEN_ERROR",
                "CLIENT_LOGIN", "CLIENT_LOGIN_ERROR",
                "FEDERATED_IDENTITY_LINK", "FEDERATED_IDENTITY_LINK_ERROR",
                "REMOVE_FEDERATED_IDENTITY", "REMOVE_FEDERATED_IDENTITY_ERROR",
                "UPDATE_EMAIL", "UPDATE_EMAIL_ERROR",
                "UPDATE_PROFILE", "UPDATE_PROFILE_ERROR",
                "UPDATE_PASSWORD", "UPDATE_PASSWORD_ERROR",
                "UPDATE_TOTP", "UPDATE_TOTP_ERROR",
                "VERIFY_EMAIL", "VERIFY_EMAIL_ERROR",
                "VERIFY_PROFILE", "VERIFY_PROFILE_ERROR",
                "REMOVE_TOTP", "REMOVE_TOTP_ERROR",
                "GRANT_CONSENT", "GRANT_CONSENT_ERROR",
                "UPDATE_CONSENT", "UPDATE_CONSENT_ERROR",
                "REVOKE_GRANT", "REVOKE_GRANT_ERROR",
                "SEND_VERIFY_EMAIL", "SEND_VERIFY_EMAIL_ERROR",
                "SEND_RESET_PASSWORD", "SEND_RESET_PASSWORD_ERROR",
                "SEND_IDENTITY_PROVIDER_LINK", "SEND_IDENTITY_PROVIDER_LINK_ERROR",
                "RESET_PASSWORD", "RESET_PASSWORD_ERROR",
                "RESTART_AUTHENTICATION", "RESTART_AUTHENTICATION_ERROR",
                "IDENTITY_PROVIDER_LINK_ACCOUNT", "IDENTITY_PROVIDER_LINK_ACCOUNT_ERROR",
                "IDENTITY_PROVIDER_FIRST_LOGIN", "IDENTITY_PROVIDER_FIRST_LOGIN_ERROR",
                "IDENTITY_PROVIDER_POST_LOGIN", "IDENTITY_PROVIDER_POST_LOGIN_ERROR",
                "IMPERSONATE", "IMPERSONATE_ERROR",
                "CUSTOM_REQUIRED_ACTION", "CUSTOM_REQUIRED_ACTION_ERROR",
                "EXECUTE_ACTIONS", "EXECUTE_ACTIONS_ERROR",
                "EXECUTE_ACTION_TOKEN", "EXECUTE_ACTION_TOKEN_ERROR",
                "CLIENT_REGISTER", "CLIENT_REGISTER_ERROR",
                "CLIENT_UPDATE", "CLIENT_UPDATE_ERROR",
                "CLIENT_DELETE", "CLIENT_DELETE_ERROR",
                "CLIENT_INITIATED_ACCOUNT_LINKING", "CLIENT_INITIATED_ACCOUNT_LINKING_ERROR",
                "TOKEN_EXCHANGE", "TOKEN_EXCHANGE_ERROR",
                "OAUTH2_DEVICE_AUTH", "OAUTH2_DEVICE_AUTH_ERROR",
                "OAUTH2_DEVICE_VERIFY_USER_CODE", "OAUTH2_DEVICE_VERIFY_USER_CODE_ERROR",
                "OAUTH2_DEVICE_CODE_TO_TOKEN", "OAUTH2_DEVICE_CODE_TO_TOKEN_ERROR",
                "AUTHREQID_TO_TOKEN", "AUTHREQID_TO_TOKEN_ERROR",
                "PERMISSION_TOKEN", "DELETE_ACCOUNT", "DELETE_ACCOUNT_ERROR",
            ],
        })
        logger.info("Configured event listeners for realm '%s'", realm)

    def ensure_user_attribute(self, realm: str, attribute_config: dict) -> None:
        self._switch_realm(realm)
        attr_name = attribute_config["name"]
        profile = self._admin.get_realm_users_profile()
        if not profile.get("attributes"):
            profile["attributes"] = []
        if any(a.get("name") == attr_name for a in profile["attributes"]):
            logger.info("User attribute '%s' already exists", attr_name)
            return
        new_attr = {"name": attr_name, "permissions": attribute_config.get("permissions", {})}
        if "display_name" in attribute_config:
            new_attr["displayName"] = attribute_config["display_name"]
        profile["attributes"].append(new_attr)
        self._admin.update_realm_users_profile(profile)
        logger.info("Created user attribute '%s' in realm '%s'", attr_name, realm)

    def _get_token(self) -> str:
        return self._admin.connection.token["access_token"]

    def register_webhook(self, realm: str, webhook_config: dict) -> None:
        url = webhook_config.get("url", "")
        if not url:
            logger.debug("Webhook URL is empty, skipping")
            return
        events = webhook_config.get("events", [])
        self._switch_realm(realm)
        headers = {
            "Authorization": f"Bearer {self._get_token()}",
            "Content-Type": "application/json",
        }
        webhook_endpoint = f"{self._server_url}/realms/{realm}/webhooks/"

        resp = requests.get(webhook_endpoint, headers=headers, verify=False)
        if resp.status_code == 200:
            for wh in resp.json():
                if wh.get("url") == url:
                    existing_events = set(wh.get("eventTypes", []))
                    if existing_events == set(events):
                        logger.info("Webhook '%s' already registered with same events", url)
                        return
                    wh_id = wh.get("id")
                    if wh_id:
                        requests.delete(f"{webhook_endpoint}{wh_id}", headers=headers, verify=False)
                        logger.info("Deleted webhook '%s' to recreate with updated events", url)
                    break

        data = {"enabled": True, "url": url, "eventTypes": events}
        for key in ("secret", "algorithm", "retryMaxElapsedSeconds", "retryMaxIntervalSeconds"):
            if key in webhook_config:
                data[key] = webhook_config[key]
        resp = requests.post(webhook_endpoint, headers=headers, json=data, verify=False)
        if resp.status_code == 201:
            logger.info("Registered webhook '%s'", url)
        else:
            logger.error("Failed to register webhook '%s': %s", url, resp.text)

    def configure_backchannel_logout(self, realm: str, client_uuid: str, url: str) -> None:
        self._switch_realm(realm)
        client = self._admin.get_client(client_uuid)
        attrs = client.get("attributes", {})
        attrs["backchannel.logout.url"] = url
        self._admin.update_client(client_uuid, {"attributes": attrs})
        logger.info("Set backchannel logout URL for client '%s'", client_uuid)

    def disable_frontchannel_logout(self, realm: str, client_uuid: str) -> None:
        self._switch_realm(realm)
        client = self._admin.get_client(client_uuid)
        client["frontchannelLogout"] = False
        attrs = client.get("attributes", {})
        attrs["frontchannel.logout.url"] = ""
        client["attributes"] = attrs
        self._admin.update_client(client_uuid, client)
        logger.info("Disabled frontchannel logout for client '%s'", client_uuid)

    def reset_admin_password(self, realm: str, username: str, password: str,
                             temporary: bool = False) -> None:
        self._switch_realm(realm)
        users = self._admin.get_users(query={"username": username, "exact": True})
        user = next((u for u in users if u["username"] == username), None)
        if not user:
            logger.warning("User '%s' not found in realm '%s', cannot reset password", username, realm)
            return
        self._admin.set_user_password(user["id"], password, temporary=temporary)
        logger.info("Reset password for '%s' in realm '%s'", username, realm)
