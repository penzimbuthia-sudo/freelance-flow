import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def configuration():
    # Load exactly the selected file, including when started without the Flask CLI.
    env_file = Path(os.getenv("FF_ENV_FILE", ".env"))
    env_file = env_file if env_file.is_absolute() else ROOT / env_file
    if "FF_ENV_FILE" in os.environ and not env_file.is_file():
        raise ValueError("The explicitly selected FF_ENV_FILE does not exist. No database was initialized.")
    # Hosted containers use injected runtime variables, not baked-in dotenv files.
    hosted = os.getenv("APP_ENV") == "production" or os.getenv("RENDER") == "true"
    if not hosted or "FF_ENV_FILE" in os.environ:
        load_dotenv(env_file, override=False)
    hosted = os.getenv("APP_ENV") == "production" or os.getenv("RENDER") == "true"
    db_path = Path(os.getenv("DATABASE_PATH", "instance/freelance-flow.sqlite3"))
    origin = os.getenv("PUBLIC_BASE_URL", "http://localhost:5173").rstrip("/")
    default_hosts = urlsplit(origin).hostname if hosted else "localhost,127.0.0.1,[::1]"
    return {
        "HOSTED": hosted,
        "AUTH_REQUIRED": hosted or bool(os.getenv("ADMIN_PASSWORD_HASH")),
        "SECRET_KEY": os.getenv("SECRET_KEY", ""),
        "ADMIN_USERNAME": os.getenv("ADMIN_USERNAME", "").strip(),
        "ADMIN_PASSWORD_HASH": os.getenv("ADMIN_PASSWORD_HASH", ""),
        "DATABASE": str(db_path if db_path.is_absolute() else ROOT / db_path),
        "DATABASE_URL": os.getenv("DATABASE_URL", "").strip(),
        "GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY", "").strip()
        or os.getenv("GEMINI_API_KEY", "").strip(),
        "GEMINI_MODEL": os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip() or "gemini-3.5-flash-lite",
        "PAYPAL_CLIENT_ID": os.getenv("PAYPAL_CLIENT_ID", "").strip(),
        "PAYPAL_CLIENT_SECRET": os.getenv("PAYPAL_CLIENT_SECRET", "").strip(),
        "PAYPAL_MERCHANT_ID": os.getenv("PAYPAL_MERCHANT_ID", "").strip(),
        "PUBLIC_BASE_URL": origin,
        "MAX_CONTENT_LENGTH": 16 * 1024,
        "TRUSTED_HOSTS": [host.strip() for host in os.getenv("APP_HOSTS", default_hosts or "").split(",") if host.strip()],
    }


def validate_configuration(config):
    """Fail before opening a database; diagnostics contain names, not values."""
    if config["HOSTED"]:
        config["AUTH_REQUIRED"] = True
        if not config.get("DATABASE_URL", "").startswith(("postgresql://", "postgres://")):
            raise ValueError("Hosted production requires a PostgreSQL DATABASE_URL; SQLite fallback is forbidden.")
        origin = urlsplit(config["PUBLIC_BASE_URL"])
        if (origin.scheme != "https" or not origin.hostname or origin.username or origin.password
                or origin.path or origin.query or origin.fragment
                or origin.hostname in ("localhost", "127.0.0.1", "::1")
                or origin.hostname.endswith(".localhost")):
            raise ValueError("Hosted PUBLIC_BASE_URL must be a public HTTPS origin without a path.")
        if not config["TRUSTED_HOSTS"] or any(host.startswith(".") or "*" in host for host in config["TRUSTED_HOSTS"]):
            raise ValueError("Hosted APP_HOSTS must contain exact hostnames, not wildcards.")
        if origin.hostname not in config["TRUSTED_HOSTS"]:
            raise ValueError("APP_HOSTS must include the PUBLIC_BASE_URL hostname.")
    if config["AUTH_REQUIRED"]:
        if len(config.get("SECRET_KEY", "")) < 32:
            raise ValueError("Login requires a random SECRET_KEY of at least 32 characters.")
        username = config.get("ADMIN_USERNAME", "")
        if not username or len(username) > 120 or any(ord(char) < 32 for char in username):
            raise ValueError("Login requires ADMIN_USERNAME (maximum 120 characters).")
        password_hash = config.get("ADMIN_PASSWORD_HASH", "")
        # Only the documented, bounded-cost Werkzeug scrypt format is accepted.
        import re
        if not re.fullmatch(r"scrypt:32768:8:1\$[A-Za-z0-9]{16,}\$[0-9a-f]{128}", password_hash):
            raise ValueError("ADMIN_PASSWORD_HASH must be a Werkzeug default scrypt hash, not a plaintext password.")
