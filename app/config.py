import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuration settings from environment variables"""

    # --- Database ---
    DATABASE_URL = os.getenv("DATABASE_URL")

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
    GMAIL_SENDER_EMAIL = os.getenv("GMAIL_SENDER_EMAIL")
    GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

    # --- AI (optional) ---
    GOOGLE_VISION_CREDENTIALS_PATH = os.getenv("GOOGLE_VISION_CREDENTIALS_PATH")

    # --- Validation ---
    if not DATABASE_URL:
        raise ValueError("DATABASE_URL not found in .env file")
    if not JWT_SECRET:
        raise ValueError("JWT_SECRET not found in .env file")
    if not CLOUDINARY_CLOUD_NAME:
        raise ValueError("CLOUDINARY_CLOUD_NAME not found in .env file")
    if not CLOUDINARY_API_KEY:
        raise ValueError("CLOUDINARY_API_KEY not found in .env file")
    if not CLOUDINARY_API_SECRET:
        raise ValueError("CLOUDINARY_API_SECRET not found in .env file")
    if not PAYSTACK_SECRET_KEY:
        raise ValueError("PAYSTACK_SECRET_KEY not found in .env file")
    if not GMAIL_SENDER_EMAIL:
        raise ValueError("GMAIL_SENDER_EMAIL not found in .env file")
    if not GMAIL_APP_PASSWORD:
        raise ValueError("GMAIL_APP_PASSWORD not found in .env file")


config = Config()
