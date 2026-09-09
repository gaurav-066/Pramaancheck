import json
import os
from pathlib import Path
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

CONFIG_PATH = Path(__file__).parent / "config.json"

# ---------------------------------------------------------------------------
# Safe lazy config loader — never crashes at import time even without config.json
# ---------------------------------------------------------------------------

_CONFIG: dict | None = None


def _get_config() -> dict:
    global _CONFIG
    if _CONFIG is None:
        _CONFIG = {}
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    _CONFIG = json.load(f)
            except Exception:
                _CONFIG = {}
    return _CONFIG


def _get_secret_key() -> str:
    return (
        os.environ.get("SESSION_SECRET")
        or _get_config().get("session_secret", "pramaancheck-dev-secret-2026")
    )


def _get_users() -> dict:
    config_users = _get_config().get("users", {})
    if config_users:
        return config_users
    # Fall back to env-variable-overridable demo accounts
    return {
        "admin": {
            "password": os.environ.get("ADMIN_PASSWORD", "admin123"),
            "role": "admin",
            "name": "Admin Authority",
        },
        "inspector": {
            "password": os.environ.get("INSPECTOR_PASSWORD", "inspect123"),
            "role": "inspector",
            "name": "Inspector Sharma",
        },
        "viewer": {
            "password": os.environ.get("VIEWER_PASSWORD", "view123"),
            "role": "viewer",
            "name": "Viewer Patel",
        },
    }


def _get_max_age_seconds() -> int:
    hours = int(
        os.environ.get("SESSION_MAX_AGE_HOURS")
        or _get_config().get("session_max_age_hours", 24)
    )
    return hours * 3600


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def authenticate_user(username: str, password: str):
    """
    Validates username and password against configured users.
    Returns user dict with username, role, name if valid, else None.
    """
    users = _get_users()
    user_data = users.get(username)
    if not user_data:
        return None
    if user_data.get("password") == password:
        return {
            "username": username,
            "role": user_data.get("role", "viewer"),
            "name": user_data.get("name", username),
        }
    return None


def create_session_token(username: str, role: str) -> str:
    """
    Generates a secure, signed session token containing username and role.
    """
    serializer = URLSafeTimedSerializer(_get_secret_key())
    return serializer.dumps({"username": username, "role": role})


def verify_session_token(token: str):
    """
    Verifies signed session token. Returns payload dict or None if invalid/expired.
    """
    if not token:
        return None
    try:
        serializer = URLSafeTimedSerializer(_get_secret_key())
        return serializer.loads(token, max_age=_get_max_age_seconds())
    except (BadSignature, SignatureExpired):
        return None


def check_permission(user_role: str, required_role: str) -> bool:
    """
    Role hierarchy: admin > inspector > viewer.
    Returns True if user_role satisfies required_role.
    """
    hierarchy = {"admin": 3, "inspector": 2, "viewer": 1}
    user_level = hierarchy.get(user_role, 0)
    required_level = hierarchy.get(required_role, 0)
    return user_level >= required_level
