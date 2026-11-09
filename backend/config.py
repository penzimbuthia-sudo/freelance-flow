import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def configuration():
    load_dotenv(ROOT / ".env", override=False)
    db_path = Path(os.getenv("DATABASE_PATH", "instance/freelance-flow.sqlite3"))
    return {
        "DATABASE": str(db_path if db_path.is_absolute() else ROOT / db_path),
        "GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY", "").strip()
        or os.getenv("GEMINI_API_KEY", "").strip(),
        "GEMINI_MODEL": os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite").strip(),
        "PAYPAL_CLIENT_ID": os.getenv("PAYPAL_CLIENT_ID", "").strip(),
        "PAYPAL_CLIENT_SECRET": os.getenv("PAYPAL_CLIENT_SECRET", "").strip(),
        "PAYPAL_MERCHANT_ID": os.getenv("PAYPAL_MERCHANT_ID", "").strip(),
        "PUBLIC_BASE_URL": os.getenv("PUBLIC_BASE_URL", "http://localhost:5173").rstrip("/"),
        "MAX_CONTENT_LENGTH": 16 * 1024,
        "TRUSTED_HOSTS": [host.strip() for host in os.getenv("APP_HOSTS", "localhost,127.0.0.1,[::1]").split(",") if host.strip()],
    }
