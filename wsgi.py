"""Gunicorn WSGI entry point. Application creation never starts a dev server."""

from backend import create_app

app = create_app()
