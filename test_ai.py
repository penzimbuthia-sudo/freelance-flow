"""Live Gemini smoke test; deliberately separate from mocked automated tests."""
from datetime import timedelta

from backend.ai import generate_message
from backend.config import configuration
from backend.errors import AppError
from backend.models import today


def main():
    config = configuration()
    try:
        text = generate_message({
            "client_name": "Alex Demo", "service_description": "fictional website design",
            "amount": "50.00", "currency": "USD", "payment_status": "unpaid",
            "due_date": (today() - timedelta(days=1)).isoformat(),
            "today": today().isoformat(), "overdue": True,
        }, config["GOOGLE_API_KEY"], config["GEMINI_MODEL"])
    except AppError as error:
        print(f"Live Gemini smoke test blocked/failed [{error.code}]: {error.message}")
        return 1
    print(f'Real Gemini output ({config["GEMINI_MODEL"]}):\n\n{text}')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
