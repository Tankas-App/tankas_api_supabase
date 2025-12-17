from app.database import supabase
from app.utils.hashing import PasswordHasher
from app.utils.validators import DataValidator
from app.utils.jwt_handler import JWTHandler
from datetime import datetime

class AuthService:
    """Handle user authentication: signup, login, and user verification"""
    
    def __init__(self):
        """Use the singleton Supabase client"""
        self.supabase = supabase
    
    async def signup(self, email: str, username: str, password: str, display_name: str = None):
        """
        Register a new user
        
        Args:
            email: User's email
            username: Unique username
            password: Plaintext password (will be hashed)
            display_name: Optional display name
            
        Returns:
            Dict with user data and JWT token
            
        Raises:
            ValueError: If validation fails or user already exists
        """
        # Step 1: Validate input
        is_valid, error_msg = DataValidator.validate_signup_input(email, username, password)
        if not is_valid:
            raise ValueError(error_msg)
        
        # Step 2: Check if username already exists
        try:
            response = self.supabase.table('users').select('id').eq('username', username).execute()
            if response.data and len(response.data) > 0:
                raise ValueError("Username already taken")
        except Exception as e:
            raise Exception(f"Database error checking username: {str(e)}")
        
        # Step 3: Check if email already exists
        try:
            response = self.supabase.table('users').select('id').eq('email', email).execute()
            if response.data and len(response.data) > 0:
                raise ValueError("Email already registered")
        except Exception as e:
            raise Exception(f"Database error checking email: {str(e)}")
        
        # Step 4: Hash the password
        hashed_password = PasswordHasher.hash_password(password)
        
        # Step 5: Create user in database
        try:
            user_data = {
                'email': email,
                'username': username,
                'password_hash': hashed_password,
                'display_name': display_name or username,  # Default to username if no display name
                'email_verified': True,  # For now, auto-verify (add real email verification later)
                'created_at': datetime.utcnow().isoformat()
            }
            
            response = self.supabase.table('users').insert(user_data).execute()
            
            if not response.data or len(response.data) == 0:
                raise Exception("Failed to create user")
            
            created_user = response.data[0]
            
        except Exception as e:
            raise Exception(f"Error creating user: {str(e)}")
        
        # Step 6: Create JWT token
        token = JWTHandler.create_token(created_user['id'], created_user['username'])
        
        # Step 7: Return user data and token
        return {
            'user': {
                'id': created_user['id'],
                'email': created_user['email'],
                'username': created_user['username'],
                'display_name': created_user['display_name'],
                'avatar_url': created_user.get('avatar_url'),
                'total_points': created_user.get('total_points', 0),
                'badge_tier': created_user.get('badge_tier', 'bronze'),
                'role': created_user.get('role', 'user'),
                'created_at': created_user['created_at']
            },
            'token': token,
            'token_type': 'bearer'
        }
    
    async def login(self, username: str, password: str):
        """
        Login a user (username or email)
        
        Args:
            username: Username or email
            password: Plaintext password
            
        Returns:
            Dict with user data and JWT token
            
        Raises:
            ValueError: If credentials are invalid
        """
        # Step 1: Find user by username OR email
        try:
            # Try to find by username first
            response = self.supabase.table('users').select('*').eq('username', username).execute()
            
            # If not found, try email
            if not response.data or len(response.data) == 0:
                response = self.supabase.table('users').select('*').eq('email', username).execute()
            
            if not response.data or len(response.data) == 0:
                raise ValueError("Username or email not found")
            
            user = response.data[0]
            
        except ValueError as e:
            raise e
        except Exception as e:
            raise Exception(f"Database error: {str(e)}")
        
        # Step 2: Verify password
        if not PasswordHasher.verify_password(password, user['password_hash']):
            raise ValueError("Invalid password")
        
        # Step 3: Create JWT token
        token = JWTHandler.create_token(user['id'], user['username'])
        
        # Step 4: Return user data and token
        return {
            'user': {
                'id': user['id'],
                'email': user['email'],
                'username': user['username'],
                'display_name': user['display_name'],
                'avatar_url': user.get('avatar_url'),
                'total_points': user.get('total_points', 0),
                'badge_tier': user.get('badge_tier', 'bronze'),
                'role': user.get('role', 'user'),
                'created_at': user['created_at']
            },
            'token': token,
            'token_type': 'bearer'
        }
    
    async def get_user_by_id(self, user_id: str):
        """
        Get user data by ID
        
        Args:
            user_id: The user's UUID
            
        Returns:
            User data dict
            
        Raises:
            ValueError: If user not found
        """
        try:
            response = self.supabase.table('users').select('*').eq('id', user_id).execute()
            
            if not response.data or len(response.data) == 0:
                raise ValueError("User not found")
            
            user = response.data[0]
            
            return {
                'id': user['id'],
                'email': user['email'],
                'username': user['username'],
                'display_name': user['display_name'],
                'avatar_url': user.get('avatar_url'),
                'total_points': user.get('total_points', 0),
                'badge_tier': user.get('badge_tier', 'bronze'),
                'role': user.get('role', 'user'),
                'created_at': user['created_at']
            }
        except ValueError as e:
            raise e
        except Exception as e:
            raise Exception(f"Database error: {str(e)}")