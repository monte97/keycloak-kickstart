"""Loads a YAML seed file and interpolates ${VAR} / ${VAR:-default} from env."""

import os
import re

import yaml

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")


def interpolate_env(value):
    """Interpolate ${VAR} and ${VAR:-default} in a string value.
    Non-string values are returned unchanged.
    Raises ValueError if a variable has no default and is not set.
    """
    if not isinstance(value, str):
        return value

    def _replace(match):
        expr = match.group(1)
        if ":-" in expr:
            var_name, default = expr.split(":-", 1)
            return os.environ.get(var_name, default)
        var_name = expr
        val = os.environ.get(var_name)
        if val is None:
            raise ValueError(
                f"Environment variable '{var_name}' is required but not set"
            )
        return val

    return _ENV_PATTERN.sub(_replace, value)


def _interpolate_recursive(obj):
    """Walk a nested dict/list and interpolate all string values."""
    if isinstance(obj, dict):
        return {k: _interpolate_recursive(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_interpolate_recursive(item) for item in obj]
    return interpolate_env(obj)


def load_seed(path: str) -> dict:
    """Load a seed YAML file, interpolate env vars, return the config dict."""
    if not os.path.exists(path):
        raise FileNotFoundError(f"Seed file not found: {path}")
    with open(path) as f:
        raw = yaml.safe_load(f)
    if not raw:
        raise ValueError(f"Seed file is empty: {path}")
    result = _interpolate_recursive(raw)
    validate_seed(result)
    return result


def validate_seed(seed: dict) -> None:
    """Validate seed structure: required fields and referential integrity."""
    if "realms" not in seed or not seed["realms"]:
        raise ValueError("Seed must contain a non-empty 'realms' list")

    for realm in seed["realms"]:
        if "name" not in realm:
            raise ValueError("Each realm must have a 'name' field")
        if "clients" not in realm or not realm["clients"]:
            raise ValueError(
                f"Realm '{realm['name']}' must have a non-empty 'clients' list"
            )

        defined_roles = set()
        for client in realm["clients"]:
            for role in client.get("roles", []):
                defined_roles.add(role)

        defined_groups = {g["name"] for g in realm.get("groups", [])}

        for i, wh in enumerate(realm.get("webhooks", [])):
            if "url" not in wh or not wh["url"]:
                raise ValueError(
                    f"Webhook #{i+1} in realm '{realm['name']}' must have a 'url'"
                )
            if "events" not in wh or not wh["events"]:
                raise ValueError(
                    f"Webhook '{wh['url']}' in realm '{realm['name']}' must have "
                    f"a non-empty 'events' list"
                )
            if "algorithm" in wh and wh["algorithm"] not in ("HmacSHA256", "HmacSHA1"):
                raise ValueError(
                    f"Webhook '{wh['url']}': algorithm must be HmacSHA256 or HmacSHA1"
                )
            for key in ("retryMaxElapsedSeconds", "retryMaxIntervalSeconds"):
                if key in wh:
                    val = wh[key]
                    if not isinstance(val, (int, float)) or val < 1:
                        raise ValueError(
                            f"Webhook '{wh['url']}': {key} must be a positive number"
                        )

        for user in realm.get("users", []):
            for role in user.get("roles", []):
                if role not in defined_roles:
                    raise ValueError(
                        f"User '{user['username']}' references undefined role "
                        f"'{role}' in realm '{realm['name']}'"
                    )
            for group in user.get("groups", []):
                if group not in defined_groups:
                    raise ValueError(
                        f"User '{user['username']}' references undefined group "
                        f"'{group}' in realm '{realm['name']}'"
                    )
