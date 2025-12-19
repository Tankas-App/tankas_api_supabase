import os
from dotenv import load_dotenv

# Load variables from .env file
load_dotenv()

class Config:
    """Configuration settings from environment variables"""
    
    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY")
    JWT_SECRET = os.getenv("JWT_SECRET")
    GOOGLE_VISION_CREDENTIALS_PATH = os.getenv("GOOGLE_VISION_CREDENTIALS_PATH")
    CLOUDINARY_CLOUD_NAME = os.getenv("CLOUDINARY_CLOUD_NAME")
    CLOUDINARY_API_KEY = os.getenv("CLOUDINARY_API_KEY")
    CLOUDINARY_API_SECRET = os.getenv("CLOUDINARY_API_SECRET")
    
    # Validation: Make sure required variables are set
    if not SUPABASE_URL:
        raise ValueError("SUPABASE_URL not found in .env file")
    if not SUPABASE_KEY:
        raise ValueError("SUPABASE_KEY not found in .env file")
    if not JWT_SECRET:
        raise ValueError("JWT_SECRET not found in .env file")
    if not GOOGLE_VISION_CREDENTIALS_PATH:
        raise ValueError("GOOGLE_VISION_CREDENTIALS_PATH not found in .env file")
    if not CLOUDINARY_CLOUD_NAME:
        raise ValueError("CLOUDINARY_CLOUD_NAME not found in .env file")
    if not CLOUDINARY_API_KEY:
        raise ValueError("CLOUDINARY_API_KEY not found in .env file")
    if not CLOUDINARY_API_SECRET:
        raise ValueError("CLOUDINARY_API_SECRET not found in .env file")

config = Config()