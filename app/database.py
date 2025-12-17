from supabase import create_client
from app.config import config

# Create Supabase client ONCE when the app starts
# This is a singleton - all parts of the app use this same instance
supabase = create_client(config.SUPABASE_URL, config.SUPABASE_KEY)

# Export it so other files can import it
__all__ = ['supabase']