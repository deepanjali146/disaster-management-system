#!/usr/bin/env python3
"""
Startup script for the Disaster Management System
"""
import os
import sys
import subprocess
import time
from config import Config

def check_redis():
    """Check if Redis is running"""
    try:
        import redis
        r = redis.Redis.from_url(Config.REDIS_URL)
        r.ping()
        print("✅ Redis is running")
        return True
    except Exception as e:
        print(f"❌ Redis is not running: {e}")
        print("Please start Redis server or install Redis")
        return False

def start_celery_worker():
    """Start Celery worker"""
    try:
        print("🚀 Starting Celery worker...")
        subprocess.Popen([
            sys.executable, "-m", "celery", 
            "-A", "celery_config", 
            "worker", 
            "--loglevel=info",
            "--concurrency=2"
        ])
        print("✅ Celery worker started")
        return True
    except Exception as e:
        print(f"❌ Failed to start Celery worker: {e}")
        return False

def start_celery_beat():
    """Start Celery beat scheduler"""
    try:
        print("🚀 Starting Celery beat scheduler...")
        subprocess.Popen([
            sys.executable, "-m", "celery", 
            "-A", "celery_config", 
            "beat", 
            "--loglevel=info"
        ])
        print("✅ Celery beat started")
        return True
    except Exception as e:
        print(f"❌ Failed to start Celery beat: {e}")
        return False

def start_flask_app():
    """Start Flask application"""
    try:
        print("🚀 Starting Flask application...")
        os.system("python app.py")
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
    except Exception as e:
        print(f"❌ Failed to start Flask app: {e}")

def main():
    """Main startup function"""
    print("🌪️  Disaster Management System Startup")
    print("=" * 50)
    
    # Check configuration
    config_status = Config.get_config_status()
    print("\n📋 Configuration Status:")
    for key, value in config_status.items():
        status = "✅" if value else "❌"
        print(f"  {status} {key}: {value}")
    
    # Check Redis
    if not check_redis():
        print("\n⚠️  Warning: Redis is not running. SMS notifications and async tasks will not work.")
        print("   To start Redis:")
        print("   - On Windows: Download and run Redis from https://redis.io")
        print("   - On macOS: brew install redis && brew services start redis")
        print("   - On Linux: sudo apt-get install redis-server && sudo systemctl start redis")
    
    # Start services
    print("\n🚀 Starting services...")
    
    # Start Celery worker if Redis is available
    if check_redis():
        start_celery_worker()
        start_celery_beat()
        time.sleep(2)  # Give Celery time to start
    
    # Start Flask app
    start_flask_app()

if __name__ == "__main__":
    main()
