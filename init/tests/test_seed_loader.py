import os
import pytest
import tempfile
import yaml

from seed_loader import interpolate_env, load_seed, validate_seed


class TestInterpolateEnv:
    def test_simple_var(self, monkeypatch):
        monkeypatch.setenv("MY_HOST", "smtp.example.com")
        assert interpolate_env("${MY_HOST}") == "smtp.example.com"

    def test_var_with_default_uses_env(self, monkeypatch):
        monkeypatch.setenv("MY_PORT", "587")
        assert interpolate_env("${MY_PORT:-25}") == "587"

    def test_var_with_default_falls_back(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        assert interpolate_env("${MISSING_VAR:-fallback}") == "fallback"

    def test_missing_var_no_default_raises(self, monkeypatch):
        monkeypatch.delenv("MISSING_VAR", raising=False)
        with pytest.raises(ValueError, match="MISSING_VAR"):
            interpolate_env("${MISSING_VAR}")

    def test_no_interpolation_needed(self):
        assert interpolate_env("plain string") == "plain string"

    def test_multiple_vars_in_string(self, monkeypatch):
        monkeypatch.setenv("HOST", "example.com")
        monkeypatch.setenv("PORT", "8080")
        assert interpolate_env("http://${HOST}:${PORT}") == "http://example.com:8080"

    def test_non_string_passthrough(self):
        assert interpolate_env(42) == 42
        assert interpolate_env(True) is True
        assert interpolate_env(None) is None


class TestLoadSeed:
    def _write_seed(self, tmp_path, data):
        path = tmp_path / "seed.yml"
        path.write_text(yaml.dump(data))
        return str(path)

    def test_load_simple_seed(self, tmp_path, monkeypatch):
        monkeypatch.setenv("MY_PASSWORD", "secret")
        seed_path = self._write_seed(tmp_path, {
            "realms": [{
                "name": "test",
                "clients": [{"clientId": "app", "app_url": "http://localhost"}],
                "users": [{"username": "admin", "password": "${MY_PASSWORD}"}],
            }]
        })
        result = load_seed(seed_path)
        assert result["realms"][0]["users"][0]["password"] == "secret"

    def test_file_not_found_raises(self):
        with pytest.raises(FileNotFoundError):
            load_seed("/nonexistent/seed.yml")

    def test_empty_file_raises(self, tmp_path):
        path = tmp_path / "empty.yml"
        path.write_text("")
        with pytest.raises(ValueError, match="empty"):
            load_seed(str(path))


class TestValidateSeed:
    def test_valid_seed_passes(self):
        seed = {
            "realms": [{
                "name": "test",
                "clients": [{"clientId": "app", "app_url": "http://localhost", "roles": ["Admin"]}],
                "groups": [{"name": "devs"}],
                "users": [{"username": "u1", "password": "p", "roles": ["Admin"], "groups": ["devs"]}],
            }]
        }
        validate_seed(seed)

    def test_missing_realms_raises(self):
        with pytest.raises(ValueError, match="realms"):
            validate_seed({})

    def test_realm_without_name_raises(self):
        with pytest.raises(ValueError, match="name"):
            validate_seed({"realms": [{"clients": []}]})

    def test_user_references_unknown_role(self):
        seed = {
            "realms": [{
                "name": "test",
                "clients": [{"clientId": "app", "app_url": "http://localhost", "roles": ["Admin"]}],
                "users": [{"username": "u1", "password": "p", "roles": ["Nonexistent"]}],
            }]
        }
        with pytest.raises(ValueError, match="Nonexistent"):
            validate_seed(seed)

    def test_user_references_unknown_group(self):
        seed = {
            "realms": [{
                "name": "test",
                "clients": [{"clientId": "app", "app_url": "http://localhost"}],
                "groups": [{"name": "devs"}],
                "users": [{"username": "u1", "password": "p", "groups": ["unknown"]}],
            }]
        }
        with pytest.raises(ValueError, match="unknown"):
            validate_seed(seed)

    def test_realm_without_clients_raises(self):
        with pytest.raises(ValueError, match="clients"):
            validate_seed({"realms": [{"name": "test"}]})
