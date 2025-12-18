import math

class DistanceCalculator:
    """Calculate distances between geographic coordinates"""
    
    # Earth's radius in kilometers
    EARTH_RADIUS_KM = 6371
    
    @staticmethod
    def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate the great-circle distance between two points on Earth
        using the Haversine formula
        
        This is commonly used for finding distances between GPS coordinates
        
        Args:
            lat1: Latitude of point 1 (decimal degrees)
            lon1: Longitude of point 1 (decimal degrees)
            lat2: Latitude of point 2 (decimal degrees)
            lon2: Longitude of point 2 (decimal degrees)
            
        Returns:
            Distance in kilometers
            
        Example:
            >>> distance = DistanceCalculator.haversine(5.6037, -0.1870, 5.6050, -0.1865)
            >>> print(f"Distance: {distance:.2f} km")  # ~0.13 km apart
        """
        # Convert degrees to radians
        lat1_rad = math.radians(lat1)
        lon1_rad = math.radians(lon1)
        lat2_rad = math.radians(lat2)
        lon2_rad = math.radians(lon2)
        
        # Differences
        dlat = lat2_rad - lat1_rad
        dlon = lon2_rad - lon1_rad
        
        # Haversine formula
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2) ** 2
        c = 2 * math.asin(math.sqrt(a))
        
        distance = DistanceCalculator.EARTH_RADIUS_KM * c
        
        return distance
    
    @staticmethod
    def is_within_radius(
        lat1: float,
        lon1: float,
        lat2: float,
        lon2: float,
        radius_km: float
    ) -> bool:
        """
        Check if two coordinates are within a certain radius of each other
        
        Args:
            lat1: Latitude of point 1
            lon1: Longitude of point 1
            lat2: Latitude of point 2
            lon2: Longitude of point 2
            radius_km: Radius in kilometers
            
        Returns:
            True if distance between points is <= radius_km
        """
        distance = DistanceCalculator.haversine(lat1, lon1, lat2, lon2)
        return distance <= radius_km