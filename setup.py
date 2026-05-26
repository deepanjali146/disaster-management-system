#!/usr/bin/env python3
"""
Setup script for Disaster Management System
"""
import os
import sys
from config import Config

def create_env_file():
    """Create .env file from template"""
    env_content = """# Disaster Management System Environment Variables
# Copy this file to .env and fill in your actual values

# Supabase Configuration
SUPABASE_URL=your_supabase_project_url_here
SUPABASE_KEY=your_supabase_anon_key_here

# Weather API Configuration (OpenWeatherMap) - Optional
WEATHER_API_KEY=your_openweathermap_api_key_here

# Flask Configuration
FLASK_SECRET_KEY=disaster_is_the_key

# Instructions:
# 1. Replace the placeholder values above with your actual credentials
# 2. For Supabase: Get these from your Supabase project dashboard
# 3. For Weather API: Optional - the app works with free APIs too
# 4. Never commit this file to version control
"""
    
    if os.path.exists('.env'):
        print("⚠  .env file already exists. Skipping creation.")
        return False
    
    try:
        with open('.env', 'w') as f:
            f.write(env_content)
        print("✅ Created .env file from template")
        print("📝 Please edit .env file with your actual credentials")
        return True
    except Exception as e:
        print(f"❌ Error creating .env file: {e}")
        return False

def check_configuration():
    """Check current configuration status"""
    print("🔍 Checking configuration...")
    
    status = Config.get_config_status()
    
    print(f"📊 Configuration Status:")
    print(f"   Supabase configured: {'✅' if status['supabase_configured'] else '❌'}")
    print(f"   Weather API configured: {'✅' if status['weather_api_configured'] else '❌'}")
    print(f"   Supabase URL set: {'✅' if status['supabase_url_set'] else '❌'}")
    print(f"   Supabase Key set: {'✅' if status['supabase_key_set'] else '❌'}")
    print(f"   Weather API Key set: {'✅' if status['weather_api_key_set'] else '❌'}")
    
    return status

def test_weather_api():
    """Test weather API functionality"""
    print("\n🌤  Testing weather API...")
    
    try:
        from test_free_weather import test_free_weather_api
        success = test_free_weather_api()
        if success:
            print("✅ Weather API is working correctly!")
        else:
            print("❌ Weather API test failed")
        return success
    except Exception as e:
        print(f"❌ Error testing weather API: {e}")
        return False

def main():
    """Main setup function"""
    print("🚀 Disaster Management System Setup")
    print("=" * 50)
    
    # Create .env file if it doesn't exist
    env_created = create_env_file()
    
    # Check configuration
    status = check_configuration()
    
    # Test weather API
    weather_ok = test_weather_api()
    
    print("\n" + "=" * 50)
    print("📋 Setup Summary:")
    
    if not status['supabase_configured']:
        print("⚠  Supabase not configured - database features will be disabled")
        print("   To enable: Edit .env file with your Supabase credentials")
    
    if not status['weather_api_configured']:
        print("ℹ  Weather API not configured - using free APIs")
        print("   To use OpenWeatherMap: Add your API key to .env file")
    
    if weather_ok:
        print("✅ Weather functionality is working")
    else:
        print("❌ Weather functionality needs attention")
    
    print("\n🎯 Next Steps:")
    print("1. Edit .env file with your Supabase credentials (optional)")
    print("2. Run 'python app.py' to start the application")
    print("3. Visit http://127.0.0.1:5000 in your browser")
    
    if env_created:
        print("\n💡 Tip: The .env file has been created. Please edit it with your actual credentials.")

if __name__ == "__main__":
    main()