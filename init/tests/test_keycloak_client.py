import pytest
from unittest.mock import MagicMock, patch
from keycloak import KeycloakGetError

from keycloak_client import KeycloakConfigurator


@pytest.fixture
def configurator():
    with patch("keycloak_client.KeycloakAdmin") as MockAdmin:
        mock_admin = MockAdmin.return_value
        cfg = KeycloakConfigurator(
            server_url="http://kc:8080/auth",
            admin_user="admin",
            admin_password="admin1234",
        )
        yield cfg, mock_admin


class TestEnsureRealm:
    def test_creates_realm_if_not_exists(self, configurator):
        cfg, mock_admin = configurator
        mock_admin.get_realms.return_value = [{"realm": "master"}]
        cfg.ensure_realm("builder")
        mock_admin.create_realm.assert_called_once()
        payload = mock_admin.create_realm.call_args[0][0]
        assert payload["realm"] == "builder"
        assert payload["enabled"] is True

    def test_skips_realm_if_exists(self, configurator):
        cfg, mock_admin = configurator
        mock_admin.get_realms.return_value = [{"realm": "master"}, {"realm": "builder"}]
        cfg.ensure_realm("builder")
        mock_admin.create_realm.assert_not_called()


class TestEnsureClient:
    def test_creates_client_if_not_exists(self, configurator):
        cfg, mock_admin = configurator
        mock_admin.get_clients.return_value = []
        mock_admin.create_client.return_value = "client-uuid"
        result = cfg.ensure_client("builder", "myapp", app_url="http://localhost")
        mock_admin.create_client.assert_called_once()
        payload = mock_admin.create_client.call_args[0][0]
        assert payload["clientId"] == "myapp"
        assert payload["redirectUris"] == ["http://localhost/*"]
        assert payload["webOrigins"] == ["http://localhost"]

    def test_returns_existing_client_id(self, configurator):
        cfg, mock_admin = configurator
        mock_admin.get_clients.return_value = [{"id": "existing-uuid", "clientId": "myapp"}]
        result = cfg.ensure_client("builder", "myapp", app_url="http://localhost")
        assert result == "existing-uuid"
        mock_admin.create_client.assert_not_called()


class TestEnsureRole:
    def test_creates_role_if_not_exists(self, configurator):
        cfg, mock_admin = configurator
        mock_admin.get_client_roles.return_value = []
        cfg.ensure_role("builder", "client-uuid", "Admin")
        mock_admin.create_client_role.assert_called_once()

    def test_skips_role_if_exists(self, configurator):
        cfg, mock_admin = configurator
        mock_admin.get_client_roles.return_value = [{"name": "Admin"}]
        cfg.ensure_role("builder", "client-uuid", "Admin")
        mock_admin.create_client_role.assert_not_called()


class TestEnsureGroup:
    def test_creates_group_if_not_exists(self, configurator):
        cfg, mock_admin = configurator
        mock_admin.get_groups.return_value = []
        mock_admin.create_group.return_value = "group-uuid"
        result = cfg.ensure_group("builder", "engineers")
        mock_admin.create_group.assert_called_once()

    def test_returns_existing_group_id(self, configurator):
        cfg, mock_admin = configurator
        mock_admin.get_groups.return_value = [{"id": "g-uuid", "name": "engineers"}]
        result = cfg.ensure_group("builder", "engineers")
        assert result == "g-uuid"
        mock_admin.create_group.assert_not_called()


class TestEnsureUser:
    def test_creates_user_if_not_exists(self, configurator):
        cfg, mock_admin = configurator
        mock_admin.get_users.return_value = []
        mock_admin.create_user.return_value = "user-uuid"
        result = cfg.ensure_user("builder", "root", "rootpass")
        mock_admin.create_user.assert_called_once()

    def test_returns_existing_user_id(self, configurator):
        cfg, mock_admin = configurator
        mock_admin.get_users.return_value = [{"id": "u-uuid", "username": "root"}]
        result = cfg.ensure_user("builder", "root", "rootpass")
        assert result == "u-uuid"
        mock_admin.create_user.assert_not_called()


class TestAssignRoleToUser:
    def test_assigns_role(self, configurator):
        cfg, mock_admin = configurator
        mock_admin.get_client_role.return_value = {"id": "role-id", "name": "Admin"}
        cfg.assign_role_to_user("builder", "user-uuid", "client-uuid", "Admin")
        mock_admin.assign_client_role.assert_called_once()


class TestAddUserToGroup:
    def test_adds_to_group(self, configurator):
        cfg, mock_admin = configurator
        cfg.add_user_to_group("builder", "user-uuid", "group-uuid")
        mock_admin.group_user_add.assert_called_once_with("user-uuid", "group-uuid")


class TestEnsureClientScope:
    def test_creates_scope_if_not_exists(self, configurator):
        cfg, mock_admin = configurator
        mock_admin.get_client_scopes.return_value = []
        mock_admin.create_client_scope.return_value = "scope-uuid"
        result = cfg.ensure_client_scope("builder", "role")
        mock_admin.create_client_scope.assert_called_once()

    def test_returns_existing_scope_id(self, configurator):
        cfg, mock_admin = configurator
        mock_admin.get_client_scopes.return_value = [{"id": "s-uuid", "name": "role"}]
        result = cfg.ensure_client_scope("builder", "role")
        assert result == "s-uuid"
        mock_admin.create_client_scope.assert_not_called()


class TestConfigureSmtp:
    def test_sets_smtp_config(self, configurator):
        cfg, mock_admin = configurator
        smtp = {"host": "smtp.local", "port": 587, "sender": "a@b.c",
                "username": "", "password": "", "ssl": False, "starttls": True}
        cfg.configure_smtp("builder", smtp)
        mock_admin.update_realm.assert_called_once()
        payload = mock_admin.update_realm.call_args[1]["payload"]
        assert payload["smtpServer"]["host"] == "smtp.local"


class TestConfigureTheme:
    def test_sets_login_theme(self, configurator):
        cfg, mock_admin = configurator
        cfg.configure_theme("builder", "custom-theme")
        mock_admin.update_realm.assert_called_once()
        payload = mock_admin.update_realm.call_args[1]["payload"]
        assert payload["loginTheme"] == "custom-theme"


class TestConfigureSsl:
    def test_sets_ssl_required(self, configurator):
        cfg, mock_admin = configurator
        cfg.configure_ssl("builder", "NONE")
        mock_admin.update_realm.assert_called_once()
        payload = mock_admin.update_realm.call_args[1]["payload"]
        assert payload["sslRequired"] == "NONE"


class TestConfigureEvents:
    def test_enables_event_listeners(self, configurator):
        cfg, mock_admin = configurator
        cfg.configure_events("builder")
        mock_admin.update_realm.assert_called_once()
        payload = mock_admin.update_realm.call_args[1]["payload"]
        assert "ext-event-webhook" in payload["eventsListeners"]
        assert payload["adminEventsEnabled"] == "true"


class TestRegisterWebhook:
    def test_creates_webhook_if_not_exists(self, configurator):
        cfg, mock_admin = configurator
        from unittest.mock import patch as mock_patch
        with mock_patch("keycloak_client.requests") as mock_requests:
            mock_get = MagicMock()
            mock_get.status_code = 200
            mock_get.json.return_value = []
            mock_post = MagicMock()
            mock_post.status_code = 201
            mock_requests.get.return_value = mock_get
            mock_requests.post.return_value = mock_post
            mock_admin.connection.token = {"access_token": "test-token"}

            cfg.register_webhook("builder", "http://sync:8888/webhook", ["admin.USER-DELETE"])
            mock_requests.post.assert_called_once()

    def test_skips_webhook_if_exists_same_events(self, configurator):
        cfg, mock_admin = configurator
        from unittest.mock import patch as mock_patch
        with mock_patch("keycloak_client.requests") as mock_requests:
            mock_get = MagicMock()
            mock_get.status_code = 200
            mock_get.json.return_value = [{
                "url": "http://sync:8888/webhook",
                "eventTypes": ["admin.USER-DELETE"],
                "enabled": "true",
            }]
            mock_requests.get.return_value = mock_get
            mock_admin.connection.token = {"access_token": "test-token"}

            cfg.register_webhook("builder", "http://sync:8888/webhook", ["admin.USER-DELETE"])
            mock_requests.post.assert_not_called()


class TestConfigureBackchannelLogout:
    def test_sets_backchannel_url(self, configurator):
        cfg, mock_admin = configurator
        mock_admin.get_client.return_value = {"id": "c-uuid", "attributes": {}}
        cfg.configure_backchannel_logout("builder", "c-uuid", "http://api:8090/logout")
        mock_admin.update_client.assert_called_once()


class TestDisableFrontchannelLogout:
    def test_disables_frontchannel(self, configurator):
        cfg, mock_admin = configurator
        mock_admin.get_client.return_value = {
            "id": "c-uuid", "attributes": {}, "frontchannelLogout": True
        }
        cfg.disable_frontchannel_logout("builder", "c-uuid")
        mock_admin.update_client.assert_called_once()


class TestResetAdminPassword:
    def test_resets_password(self, configurator):
        cfg, mock_admin = configurator
        mock_admin.get_users.return_value = [{"id": "admin-uuid", "username": "admin"}]
        cfg.reset_admin_password("master", "admin", "newpass", temporary=False)
        mock_admin.set_user_password.assert_called_once_with("admin-uuid", "newpass", temporary=False)
