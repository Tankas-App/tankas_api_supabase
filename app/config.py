import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuration settings from environment variables"""

    # --- Database ---
    DATABASE_URL = os.getenv("DATABASE_URL")

    # TLS mode for the database connection: 'require' | 'prefer' | 'disable'.
    # Leave unset to auto-detect (see app/database.py::_resolve_ssl) — managed
    # providers get TLS, Railway's private network and local Postgres do not.
    DB_SSL = os.getenv("DB_SSL", "")

    DB_POOL_MIN = int(os.getenv("DB_POOL_MIN", "2"))
    DB_POOL_MAX = int(os.getenv("DB_POOL_MAX", "10"))

    # --- Auth ---
    JWT_SECRET = os.getenv("JWT_SECRET")

    # --- Image storage ---
    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

    # --- Payments ---
    PAYSTACK_SECRET_KEY = os.getenv("PAYSTACK_SECRET_KEY")
    PAYSTACK_BASE_URL = os.getenv("PAYSTACK_BASE_URL", "https://api.paystack.co")

    # --- Email ---
    # Two transports. Resend (HTTPS) is used when RESEND_API_KEY is set,
    # otherwise the code falls back to Gmail SMTP.
    #
    # This matters in production: Railway blocks outbound SMTP on Free, Trial
    # and Hobby plans — connections fail with "[Errno 101] Network is
    # unreachable" — so a hosted deploy has to send over HTTPS instead.
    # See https://docs.railway.com/networking/outbound-networking
    GMAIL_SENDER_EMAIL = os.getenv("GMAIL_SENDER_EMAIL")
    GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

    RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
    # Must be an address on a domain verified in Resend. The default only
    # delivers to the address that owns the Resend account — fine for testing,
    # not for real users.
    RESEND_FROM = os.getenv("RESEND_FROM", "Tankas <onboarding@resend.dev>")

    # --- AI Provider ---
    # Options: "yolo" (free, default) or "google_vision" (paid, more accurate)
    # Switch by changing this one line in .env — no code changes needed
    AI_PROVIDER = os.getenv("AI_PROVIDER", "yolo")

    # Only required when AI_PROVIDER=google_vision
    GOOGLE_VISION_CREDENTIALS_PATH = os.getenv("GOOGLE_VISION_CREDENTIALS_PATH")

    # --- Validation ---
    # Report every missing variable at once. Failing on the first one means a
    # deploy has to fail once per variable to discover them all, which is a
    # miserable loop on a hosted platform.
    _REQUIRED = (
        ("DATABASE_URL", DATABASE_URL),
        ("JWT_SECRET", JWT_SECRET),
        ("CLOUDINARY_CLOUD_NAME", CLOUDINARY_CLOUD_NAME),
        ("CLOUDINARY_API_KEY", CLOUDINARY_API_KEY),
        ("CLOUDINARY_API_SECRET", CLOUDINARY_API_SECRET),
        ("PAYSTACK_SECRET_KEY", PAYSTACK_SECRET_KEY),
        ("GMAIL_SENDER_EMAIL", GMAIL_SENDER_EMAIL),
        ("GMAIL_APP_PASSWORD", GMAIL_APP_PASSWORD),
    )

    _missing = [name for name, value in _REQUIRED if not value]

    if AI_PROVIDER == "google_vision" and not GOOGLE_VISION_CREDENTIALS_PATH:
        _missing.append("GOOGLE_VISION_CREDENTIALS_PATH (required when AI_PROVIDER=google_vision)")

    if _missing:
        raise ValueError(
            "Missing required configuration: "
            + ", ".join(_missing)
            + ". Set these as environment variables (Railway: service Variables tab) "
            "or in a local .env file. See .env.example."
        )


config = Config()
