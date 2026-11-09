import os
import sys
from getpass import getpass

from google import genai
from google.genai.errors import APIError
from google.genai.types import HttpOptions, HttpRetryOptions

MODEL = "gemini-3.5-flash-lite"
PROMPT = (
    "Write a polite payment reminder under 40 words. "
    "Client: Alex. Service: website design. "
    "Amount: USD 50. Payment was due yesterday. "
    "Do not invent a payment link."
)


def get_api_key() -> str:
    api_key = (
        os.environ.get("GOOGLE_API_KEY", "").strip()
        or os.environ.get("GEMINI_API_KEY", "").strip()
    )
    if not api_key:
        if not sys.stdin.isatty():
            raise SystemExit(
                "Set GOOGLE_API_KEY or GEMINI_API_KEY, or run this script in a "
                "terminal to enter the key securely."
            )
        api_key = getpass("Gemini API key: ").strip()

    if not api_key:
        raise SystemExit("No Gemini API key was provided.")
    return api_key


def generate_payment_reminder(api_key: str) -> str:
    client = genai.Client(
        api_key=api_key,
        http_options=HttpOptions(
            timeout=20_000,
            retry_options=HttpRetryOptions(
                attempts=2,
                initial_delay=0.5,
                max_delay=1,
                exp_base=2,
                jitter=0.2,
            )
        ),
    )
    try:
        response = client.models.generate_content(model=MODEL, contents=PROMPT)
    except APIError as error:
        raise SystemExit(
            f"Gemini API request failed after automatic retries: {error}"
        ) from error

    text = response.text
    if not text or not text.strip():
        raise SystemExit("Gemini returned an empty response.")
    return text.strip()


def main() -> None:
    reminder = generate_payment_reminder(get_api_key())
    print("\nAI response:")
    print(reminder)


if __name__ == "__main__":
    main()