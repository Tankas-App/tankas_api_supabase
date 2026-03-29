import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Configuration settings from environment variables"""

    # --- Database (Koyeb PostgreSQL) ---
    DATABASE_URL = os.getenv("DATABASE_URL")

    # --- Auth ---
    JWT_SECRET = os.getenv("JWT_SECRET")

    # --- Image storage ---
    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")

    # --- AI ---
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


config = Config()
