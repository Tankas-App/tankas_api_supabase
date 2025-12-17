import re

class DataValidator:
    """Validate user input before processing"""
    
    @staticmethod
    def is_valid_email(email: str) -> bool:
        """
        Check if email format is valid
        
        Args:
            email: The email address to validate
            
        Returns:
            True if valid email format, False otherwise
        """
        # Simple regex pattern for email validation
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None
    
    @staticmethod
    def is_valid_username(username: str) -> bool:
        """
        Check if username meets requirements
        - At least 3 characters
        - Only alphanumeric and underscores
        - Starts with letter
        
        Args:
            username: The username to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Username: 3-20 chars, starts with letter, alphanumeric + underscore
        pattern = r'^[a-zA-Z][a-zA-Z0-9_]{2,19}$'
        return re.match(pattern, username) is not None
    
    @staticmethod
    def is_valid_password(password: str) -> bool:
        """
        Check if password meets minimum requirements
        - At least 8 characters
        - Contains at least one number
        - Contains at least one uppercase letter
        
        Args:
            password: The password to validate
            
        Returns:
            True if password is strong enough, False otherwise
        """
        if len(password) < 8:
            return False
        
        # Check for at least one number
        if not re.search(r'\d', password):
            return False
        
        # Check for at least one uppercase letter
        if not re.search(r'[A-Z]', password):
            return False
        
        return True
    
    @staticmethod
    def validate_signup_input(email: str, username: str, password: str) -> tuple[bool, str]:
        """
        Validate all signup inputs together
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Validate email
        if not email or not DataValidator.is_valid_email(email):
            return False, "Invalid email format"
        
        # Validate username
        if not username or not DataValidator.is_valid_username(username):
            return False, "Username must be 3-20 characters, start with a letter, and contain only letters, numbers, or underscores"
        
        # Validate password
        if not password or not DataValidator.is_valid_password(password):
            return False, "Password must be at least 8 characters with uppercase letters and numbers"
        
        return True, ""