import bcrypt

class PasswordHasher:
    """Handle password hashing and verification using bcrypt"""
    
    @staticmethod
    def hash_password(password: str) -> str:
        """
        Hash a plaintext password using bcrypt
        
        Args:
            password: The plaintext password to hash
            
        Returns:
            The hashed password (with salt embedded)
        """
        # bcrypt.hashpw needs bytes, not strings
        password_bytes = password.encode('utf-8')
        
        # Generate a salt and hash the password
        # rounds=12 means it will take ~0.1 seconds per hash (intentionally slow for security)
        salt = bcrypt.gensalt(rounds=12)
        hashed = bcrypt.hashpw(password_bytes, salt)
        
        # Convert bytes back to string for storage in database
        return hashed.decode('utf-8')
    
    @staticmethod
    def verify_password(plain_password: str, hashed_password: str) -> bool:
        """
        Verify a plaintext password against a hashed password
        
        Args:
            plain_password: The password user enters (plaintext)
            hashed_password: The stored hash from database
            
        Returns:
            True if password matches, False otherwise
        """
        # Convert to bytes for bcrypt
        plain_bytes = plain_password.encode('utf-8')
        hashed_bytes = hashed_password.encode('utf-8')
        
        # bcrypt automatically extracts the salt from the hash and compares
        return bcrypt.checkpw(plain_bytes, hashed_bytes)