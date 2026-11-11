"""Interactive local setup; writes secrets privately, never prints them."""

from getpass import getpass
import os
from pathlib import Path
import re
import secrets

from werkzeug.security import generate_password_hash


def main():
    target = Path(__file__).resolve().parent.parent / ".env.render.local"
    if target.exists():
        raise SystemExit(".env.render.local already exists; nothing was overwritten.")
    username = input("Choose the workspace admin username: ").strip()
    if not re.fullmatch(r"[A-Za-z0-9_.@-]{1,120}", username):
        raise SystemExit("Use 1–120 letters, digits, _, ., @ or - for the username.")
    password = getpass("Choose a unique password (at least 16 characters): ")
    if not 16 <= len(password) <= 1024 or password != getpass("Confirm password: "):
        raise SystemExit("Password length/confirmation failed; no file written.")
    values = {
        "SECRET_KEY": secrets.token_urlsafe(48), "ADMIN_USERNAME": username,
        "ADMIN_PASSWORD_HASH": generate_password_hash(password),
    }
    with os.fdopen(os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as file:
        file.write("# Server-only Render login settings. Never commit or paste into chat.\n")
        for key, value in values.items():
            file.write(f"{key}={value}\n")
    print("Saved login settings privately to .env.render.local (mode 600). No password was saved or printed.")


if __name__ == "__main__":
    main()
