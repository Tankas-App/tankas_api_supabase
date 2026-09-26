import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuration settings from environment variables"""

    # --- Database ---
    DATABASE_URL = os.getenv("DATABASE_URL")

    # asyncpg only understands postgresql:// and postgres://. A SQLAlchemy-style
    # "postgresql+asyncpg://" URL (common in copy-pasted examples) makes it fail
    # with an unhelpful DSN error, so strip the driver suffix.
    if DATABASE_URL and DATABASE_URL.startswith(("postgresql+", "postgres+")):
        DATABASE_URL = "postgresql://" + DATABASE_URL.split("://", 1)[1]

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

    # Pin the transport explicitly: "resend" | "brevo" | "smtp".
    # Unset means "first one configured wins", which makes a stray RESEND_API_KEY
    # quietly override Brevo.
    EMAIL_PROVIDER = os.getenv("EMAIL_PROVIDER", "")

    RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")
    # Must be an address on a domain verified in Resend. The default only
    # delivers to the address that owns the Resend account — fine for testing,
    # not for real users.
    RESEND_FROM = os.getenv("RESEND_FROM", "Tankas <onboarding@resend.dev>")

    # Brevo is the transport that works without owning a domain: it sends to
    # anyone once a single sender *address* is verified, on a permanent free
    # tier. Used when RESEND_API_KEY is unset.
    BREVO_API_KEY = os.getenv("BREVO_API_KEY", "")
    BREVO_SENDER_EMAIL = os.getenv("BREVO_SENDER_EMAIL", "")
    BREVO_SENDER_NAME = os.getenv("BREVO_SENDER_NAME", "Tankas")

    # --- AI Provider ---
    # Options: "yolo" (free, default) or "google_vision" (paid, more accurate)
    # Switch by changing this one line in .env — no code changes needed
    AI_PROVIDER = os.getenv("AI_PROVIDER", "yolo")

    # Only required when AI_PROVIDER=google_vision. Set ONE of these:
    #   GOOGLE_VISION_CREDENTIALS_JSON — the service-account JSON itself, pasted
    #     into a variable. Use this on Railway: credentials/ is gitignored and
    #     excluded from the image, so there is no file to point at.
    #   GOOGLE_VISION_CREDENTIALS_PATH — path to the JSON file, for local runs.
    GOOGLE_VISION_CREDENTIALS_JSON = os.getenv("GOOGLE_VISION_CREDENTIALS_JSON", "")
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
    )

    _missing = [name for name, value in _REQUIRED if not value]

    # Gmail credentials only matter when SMTP is the transport. Mirrors
    # EmailService._resolve_provider: on Railway you use Resend or Brevo (SMTP
    # is blocked), and should not have to invent Gmail values to boot.
    _email_provider = EMAIL_PROVIDER.strip().lower() or (
        "resend" if RESEND_API_KEY else "brevo" if BREVO_API_KEY else "smtp"
    )
    if _email_provider == "smtp":
        _missing += [
            name
            for name, value in (
                ("GMAIL_SENDER_EMAIL", GMAIL_SENDER_EMAIL),
                ("GMAIL_APP_PASSWORD", GMAIL_APP_PASSWORD),
            )
            if not value
        ]
    elif _email_provider == "brevo" and not BREVO_SENDER_EMAIL:
        _missing.append("BREVO_SENDER_EMAIL (required when sending through Brevo)")

    if AI_PROVIDER == "google_vision" and not (
        GOOGLE_VISION_CREDENTIALS_JSON or GOOGLE_VISION_CREDENTIALS_PATH
    ):
        _missing.append(
            "GOOGLE_VISION_CREDENTIALS_JSON or GOOGLE_VISION_CREDENTIALS_PATH "
            "(required when AI_PROVIDER=google_vision)"
        )

    if _missing:
        raise ValueError(
            "Missing required configuration: "
            + ", ".join(_missing)
            + ". Set these as environment variables (Railway: service Variables tab) "
            "or in a local .env file. See .env.example."
        )


config = Config()
