# rd-auth-server/init/tests/test_init.py
import pytest
from unittest.mock import MagicMock, patch, call
import tempfile
import yaml
import os

KC_ENV = {
    "KC_ADMIN_PASSWORD": "admin1234",
    "KC_URL": "http://kc:8080/auth",
    "SEED_FILE": "/app/seed.yml",
}


class TestInitOrchestrator:
    def _write_seed(self, tmp_path, data):
        path = tmp_path / "seed.yml"
        path.write_text(yaml.dump(data))
        return str(path)

    @patch.dict(os.environ, KC_ENV)
    @patch("orchestrator.KeycloakConfigurator")
    @patch("orchestrator.wait_for_keycloak")
    @patch("orchestrator.load_seed")
    def test_full_realm_setup(self, mock_load, mock_wait, MockCfg):
        cfg = MockCfg.return_value
        cfg.ensure_client.return_value = "client-uuid"
        cfg.ensure_group.return_value = "group-uuid"
        cfg.ensure_user.return_value = "user-uuid"
        cfg.ensure_client_scope.return_value = "scope-uuid"

        mock_load.return_value = {
            "realms": [{
                "name": "test",
                "theme": "custom",
                "ssl_required": "NONE",
                "smtp": {"host": "smtp", "port": 587, "sender": "a@b.c"},
                "clients": [{
                    "clientId": "app",
                    "app_url": "http://localhost",
                    "roles": ["Admin"],
                    "scope": {"name": "role", "mapper": "client-role-mapper"},
                    "backchannel_logout_url": "http://api/logout",
                    "disable_frontchannel_logout": True,
                }],
                "groups": [{"name": "devs"}],
                "users": [{"username": "root", "password": "pass",
                           "roles": ["Admin"], "groups": ["devs"]}],
                "webhooks": [{"url": "http://sync/webhook", "events": ["admin.USER-DELETE"]}],
                "user_attributes": [{"name": "language"}],
                "admin": {"reset_password": "newpass", "temporary": False},
            }]
        }

        from orchestrator import main
        main()

        cfg.ensure_realm.assert_called_once_with("test")
        cfg.ensure_client.assert_called_once()
        cfg.ensure_role.assert_called_once_with("test", "client-uuid", "Admin")
        cfg.ensure_client_scope.assert_called_once_with("test", "role")
        cfg.create_scope_mapper.assert_called_once()
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

    @patch.dict(os.environ, KC_ENV)
    @patch("orchestrator.KeycloakConfigurator")
    @patch("orchestrator.wait_for_keycloak")
    @patch("orchestrator.load_seed")
    def test_minimal_realm_no_optional_sections(self, mock_load, mock_wait, MockCfg):
        cfg = MockCfg.return_value
        cfg.ensure_client.return_value = "client-uuid"

        mock_load.return_value = {
            "realms": [{
                "name": "minimal",
                "clients": [{"clientId": "app", "app_url": "http://localhost"}],
            }]
        }

        from orchestrator import main
        main()

        cfg.ensure_realm.assert_called_once_with("minimal")
        cfg.ensure_client.assert_called_once()
        cfg.configure_smtp.assert_not_called()
        cfg.configure_theme.assert_not_called()
        cfg.register_webhook.assert_not_called()
        cfg.ensure_user_attribute.assert_not_called()
        cfg.reset_admin_password.assert_not_called()
