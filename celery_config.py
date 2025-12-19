"""
Celery Configuration for Async Task Processing
"""
from celery import Celery
from config import Config

# Create Celery instance
celery = Celery(
    'disaster_management',
    broker=Config.REDIS_URL,
    backend=Config.REDIS_URL,
    include=['tasks']
)

# Celery configuration
celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='Asia/Kolkata',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
)

# Task routes
celery.conf.task_routes = {
    'tasks.send_sms_notification': {'queue': 'sms'},
    'tasks.process_incident_notification': {'queue': 'incidents'},
    'tasks.send_weather_alert': {'queue': 'alerts'},
}

# Beat schedule for periodic tasks
celery.conf.beat_schedule = {
    'check-weather-alerts': {
        'task': 'tasks.check_weather_alerts',
        'schedule': 300.0,  # Every 5 minutes
    },
    'cleanup-old-notifications': {
        'task': 'tasks.cleanup_old_notifications',
        'schedule': 86400.0,  # Every 24 hours
    },
}

celery.conf.timezone = 'Asia/Kolkata'
