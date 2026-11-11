import sqlite3

import click
import psycopg
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

from .config import ROOT, configuration
from .db import DatabaseConnectionError, close_db, init_db
from .errors import AppError
from .models import create_request
from .paypal import PayPalService
from .security import require_local_management


def create_app(test_config=None):
    app = Flask(__name__, static_folder=None)
    app.config.update(configuration())
    if test_config:
        app.config.update(test_config)
        # An explicitly selected local/test database must never inherit a real
        # DATABASE_URL from the developer's environment file.
        if "DATABASE" in test_config and "DATABASE_URL" not in test_config:
            app.config["DATABASE_URL"] = ""
    app.teardown_appcontext(close_db)
    with app.app_context():
        try:
            init_db()
        except psycopg.Error:
            raise DatabaseConnectionError("PostgreSQL schema initialization failed; no reset was performed. Check permissions and schema compatibility.") from None
    app.extensions["paypal"] = PayPalService(app.config)
    from .routes import api
    app.register_blueprint(api)

    @app.errorhandler(AppError)
    def app_error(error):
        details = {"code": error.code, "message": error.message}
        if error.diagnostics.get("debug_id"):
            details["debug_id"] = error.diagnostics["debug_id"]
        return jsonify({"error": details}), error.status

    @app.errorhandler(HTTPException)
    def http_error(error):
        return jsonify({"error": {"code": error.name.lower().replace(" ", "_"), "message": error.description}}), error.code

    @app.errorhandler(sqlite3.OperationalError)
    @app.errorhandler(psycopg.OperationalError)
    @app.errorhandler(DatabaseConnectionError)
    def db_error(_error):
        return jsonify({"error": {"code": "database_busy", "message": "The workspace is busy. Please retry shortly."}}), 503

    @app.errorhandler(Exception)
    def unexpected_error(error):
        # No exception body: upstream errors can contain sensitive payloads.
        app.logger.error("Unhandled application error: %s", type(error).__name__)
        return jsonify({"error": {"code": "internal_error", "message": "Something went wrong. Please retry."}}), 500

    @app.after_request
    def security_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if request.path.startswith("/api/") or request.path.startswith("/pay/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def frontend(path):
        if path.startswith("api/"):
            raise AppError("not_found", "API endpoint not found.", 404)
        dist = ROOT / "dist"
        if path and (dist / path).is_file() and (dist / path).resolve().is_relative_to(dist.resolve()):
            return send_from_directory(dist, path)
        if not path.startswith("pay/"):
            require_local_management()
        if not (dist / "index.html").exists():
            raise AppError("frontend_not_built", "Run npm run build or use the Vite development server.", 503)
        return send_from_directory(dist, "index.html")

    @app.cli.command("seed-demo")
    def seed_demo():
        """Explicitly add fictional, unpaid requests. Never invent successful payments."""
        from datetime import timedelta
        from .models import today
        from .db import get_db
        if get_db().execute("SELECT COUNT(*) AS count FROM payment_requests").fetchone()["count"]:
            click.echo("Database is not empty; no demo data added.")
            return
        for name, service, amount, days in [
            ("Alex Demo", "Fictional website design project", "250.00", 7),
            ("Sam Example", "Fictional brand identity package", "120.50", -3),
            ("Jordan Sample", "Fictional consulting session", "75.00", 0),
        ]:
            create_request({"client_name": name, "service_description": service, "amount": amount,
                            "due_date": (today() + timedelta(days=days)).isoformat()})
        click.echo("Added three fictional unpaid requests. No payments or AI responses were fabricated.")

    return app
