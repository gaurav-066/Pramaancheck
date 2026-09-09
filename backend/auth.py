import json
import os
from pathlib import Path
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

# Load config path relative to backend directory
CONFIG_PATH = Path(__file__).parent / "config.json"

def load_config():
    paths_to_check = [
        Path(__file__).parent / "config.json",
        Path(__file__).parent.parent / "config.json",
        Path("/var/task/backend/config.json"),
        Path("/var/task/config.json"),
        Path("backend/config.json"),
        Path("config.json")
    ]
    for p in paths_to_check:
        if p.exists():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
    return {
        "session_secret": "pramaancheck-secret-key-change-in-production",
        "session_max_age_hours": 24,
        "users": {
            "admin": {"password": "admin123", "role": "admin", "name": "Admin User"},
            "inspector": {"password": "inspect123", "role": "inspector", "name": "Inspector Sharma"},
            "viewer": {"password": "view123", "role": "viewer", "name": "Viewer Patel"}
        }
    }

config = load_config()

SECRET_KEY = os.environ.get("SECRET_KEY") or os.environ.get("SESSION_SECRET") or config.get("session_secret", "pramaancheck-secret-key")
SERIALIZER = URLSafeTimedSerializer(SECRET_KEY)

MAX_AGE_SECONDS = config.get("session_max_age_hours", 24) * 3600
USERS = config.get("users", {})

def authenticate_user(username: str, password: str):
    """
    Validates username and password against configured users.
    Returns user dict with username, role, name if valid, else None.
    """
    user_data = USERS.get(username)
    if not user_data:
        return None
    if user_data.get("password") == password:
        return {
            "username": username,
            "role": user_data.get("role", "viewer"),
            "name": user_data.get("name", username)
        }
    return None

def create_session_token(username: str, role: str) -> str:
    """
    Generates a secure, signed session token containing username and role.
    """
    payload = {"username": username, "role": role}
    return SERIALIZER.dumps(payload)

def verify_session_token(token: str):
    """
    Verifies signed session token. Returns payload dict or None if invalid/expired.
    """
    if not token:
        return None
    try:
        data = SERIALIZER.loads(token, max_age=MAX_AGE_SECONDS)
        return data
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
