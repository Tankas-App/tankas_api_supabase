import piexif
from PIL import Image
from io import BytesIO
from typing import Optional, Tuple

class ExifHelper:
    """Extract GPS and other metadata from image files"""
    
    @staticmethod
    def extract_gps_coordinates(image_bytes: bytes) -> Optional[Tuple[float, float]]:
        """
        Extract GPS coordinates (latitude, longitude) from image EXIF data
        
        Args:
            image_bytes: Raw image data as bytes
            
        Returns:
            Tuple of (latitude, longitude) or None if not found
            
        Raises:
            ValueError: If image is corrupted or format not supported
        """
        try:
            # Convert bytes to PIL Image
            image = Image.open(BytesIO(image_bytes))
            
            # Check if image has EXIF data
            exif_dict = piexif.load(image.info.get("exif", b""))
            
            # GPS info is in the "0th" IFD (Image File Directory)
            if "0th" not in exif_dict or piexif.ImageIFD.GPSInfo not in exif_dict["0th"]:
                return None
            
            # Extract GPS IFD (a sub-IFD containing GPS data)
            gps_ifd = exif_dict["GPS"]
            
            # GPS data format: (numerator, denominator)
            # Latitude: [degrees, minutes, seconds]
            # Longitude: [degrees, minutes, seconds]
            
            if piexif.GPSIFD.GPSLatitude not in gps_ifd or piexif.GPSIFD.GPSLongitude not in gps_ifd:
                return None
            
            # Extract latitude
            lat_data = gps_ifd[piexif.GPSIFD.GPSLatitude]
            latitude = ExifHelper._dms_to_decimal(lat_data)
            
            # Check latitude direction (North is positive, South is negative)
            if piexif.GPSIFD.GPSLatitudeRef in gps_ifd:
                lat_ref = gps_ifd[piexif.GPSIFD.GPSLatitudeRef].decode()
                if lat_ref == "S":
                    latitude = -latitude
            
            # Extract longitude
            lon_data = gps_ifd[piexif.GPSIFD.GPSLongitude]
            longitude = ExifHelper._dms_to_decimal(lon_data)
            
            # Check longitude direction (East is positive, West is negative)
            if piexif.GPSIFD.GPSLongitudeRef in gps_ifd:
                lon_ref = gps_ifd[piexif.GPSIFD.GPSLongitudeRef].decode()
                if lon_ref == "W":
                    longitude = -longitude
            
            return (latitude, longitude)
        
        except Exception as e:
            # If any error occurs (missing EXIF, corrupt file, etc.), return None
            # The frontend will fall back to geolocation
            print(f"EXIF extraction error: {str(e)}")
            return None
    
    @staticmethod
    def _dms_to_decimal(dms: list) -> float:
        """
        Convert GPS coordinates from DMS (Degrees, Minutes, Seconds) to decimal format
        
        GPS data comes in DMS format: [degrees, minutes, seconds]
        Each value is stored as a tuple: (numerator, denominator)
        
        Formula: decimal = degrees + (minutes/60) + (seconds/3600)
        
        Args:
            dms: List of 3 tuples [(deg_num, deg_den), (min_num, min_den), (sec_num, sec_den)]
            
        Returns:
            Decimal degree value
        """
        degrees = dms[0][0] / dms[0][1]
        minutes = dms[1][0] / dms[1][1]
        seconds = dms[2][0] / dms[2][1]
        
        return degrees + (minutes / 60) + (seconds / 3600)
    
    @staticmethod
    def get_image_metadata(image_bytes: bytes) -> dict:
        """
        Get all available metadata from an image
        
        Args:
            image_bytes: Raw image data as bytes
            
        Returns:
            Dictionary with metadata (size, format, GPS, etc.)
        """
        try:
            image = Image.open(BytesIO(image_bytes))
            
            metadata = {
                "format": image.format,
                "size": image.size,
                "width": image.width,
                "height": image.height,
                "gps": ExifHelper.extract_gps_coordinates(image_bytes)
            }
            
            return metadata
        except Exception as e:
            print(f"Metadata extraction error: {str(e)}")
            return {"error": str(e)}