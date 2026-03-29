import cloudinary
import cloudinary.uploader
from app.config import config
from io import BytesIO


class CloudinaryHelper:
    """Handle photo uploads to Cloudinary"""

    @staticmethod
    def initialize():
        """Initialize Cloudinary with credentials"""
        cloudinary.config(
            cloud_name=config.CLOUDINARY_CLOUD_NAME,
            api_key=config.CLOUDINARY_API_KEY,
            api_secret=config.CLOUDINARY_API_SECRET,
        )

    @staticmethod
    async def upload_photo(photo_bytes: bytes, folder: str = "tankas-issues") -> str:
        """
        Upload a photo to Cloudinary

        Args:
            photo_bytes: Raw image data as bytes
            folder: Folder path in Cloudinary (default: tankas-issues)

        Returns:
            Public URL of uploaded photo

        Raises:
            Exception: If upload fails
        """
        try:
            # Initialize if not already done
            CloudinaryHelper.initialize()

            # Convert bytes to file-like object
            file_stream = BytesIO(photo_bytes)

            # Upload to Cloudinary
            result = cloudinary.uploader.upload(
                file_stream,
                folder=folder,
                resource_type="auto",
                overwrite=False,
            )

            # Return the secure HTTPS URL
            return result.get("secure_url")

        except Exception as e:
            print(f"DEBUG: Cloudinary upload error: {e}")
            raise Exception(f"Photo upload to Cloudinary failed: {str(e)}")
