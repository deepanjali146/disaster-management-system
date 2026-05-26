"""
Configuration management for Disaster Management System
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    """Application configuration"""
    
    # Flask Configuration
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', 'disaster_is_the_key')
    
    # Supabase Configuration
    SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
    SUPABASE_KEY = os.environ.get('SUPABASE_KEY', '')
    
    # Weather API Configuration (Optional)
    WEATHER_API_KEY = os.environ.get('WEATHER_API_KEY', '')
    
    # SMS Configuration (Free API)
    SMS_API_KEY = os.environ.get('SMS_API_KEY', '')
    
    # Twilio SMS Configuration (Optional)
    TWILIO_ACCOUNT_SID = os.environ.get('TWILIO_ACCOUNT_SID', '')
    TWILIO_AUTH_TOKEN = os.environ.get('TWILIO_AUTH_TOKEN', '')
    TWILIO_PHONE_NUMBER = os.environ.get('TWILIO_PHONE_NUMBER', '')
    
    # Razorpay Configuration - fully removed (using UPI only)
    
    # Redis Configuration for Celery
    REDIS_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
    
    @classmethod
    def is_supabase_configured(cls):
        """Check if Supabase is properly configured"""
        return bool(cls.SUPABASE_URL and cls.SUPABASE_KEY)
    
    @classmethod
    def is_weather_api_configured(cls):
        """Check if weather API is configured (optional)"""
        return bool(cls.WEATHER_API_KEY and cls.WEATHER_API_KEY != 'your_openweathermap_api_key_here')
    
    @classmethod
    def is_sms_configured(cls):
        """Check if SMS service is configured"""
        return bool(cls.SMS_API_KEY or (cls.TWILIO_ACCOUNT_SID and cls.TWILIO_AUTH_TOKEN and cls.TWILIO_PHONE_NUMBER))
    
    @classmethod
    def is_twilio_configured(cls):
        """Check if Twilio is properly configured"""
        return bool(cls.TWILIO_ACCOUNT_SID and cls.TWILIO_AUTH_TOKEN and cls.TWILIO_PHONE_NUMBER)
    
    # @classmethod
    
    @classmethod
    def get_config_status(cls):
        """Get configuration status for debugging"""
        return {
            'supabase_configured': cls.is_supabase_configured(),
            'weather_api_configured': cls.is_weather_api_configured(),
            'twilio_configured': cls.is_twilio_configured(),
            # Razorpay removed
            'supabase_url_set': bool(cls.SUPABASE_URL),
            'supabase_key_set': bool(cls.SUPABASE_KEY),
            'weather_api_key_set': bool(cls.WEATHER_API_KEY),
            'twilio_sid_set': bool(cls.TWILIO_ACCOUNT_SID),
            'twilio_token_set': bool(cls.TWILIO_AUTH_TOKEN),
            'twilio_phone_set': bool(cls.TWILIO_PHONE_NUMBER),
            # Razorpay key flags removed
        }