"""
Celery Tasks for Async Processing
"""
from celery_config import celery
from sms_service import sms_service
from config import Config
from supabase import create_client, Client
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Supabase client
supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY) if Config.is_supabase_configured() else None

@celery.task(bind=True, max_retries=3)
def send_sms_notification(self, incident_id, user_phone, message):
    """
    Send SMS notification to a single user
    """
    try:
        if not sms_service.client:
            logger.error("SMS service not configured")
            return False
        
        # Send SMS
        response = sms_service.client.messages.create(
            body=message,
            from_=Config.TWILIO_PHONE_NUMBER,
            to=user_phone
        )
        
        # Log SMS
        sms_service._log_sms_notification(
            user_id=None,  # Will be updated if needed
            phone_number=user_phone,
            message=message,
            incident_id=incident_id,
            status='sent',
            twilio_sid=response.sid
        )
        
        logger.info(f"SMS sent to {user_phone}: {response.sid}")
        return True
        
    except Exception as exc:
        logger.error(f"SMS sending failed: {str(exc)}")
        
        # Log failed SMS
        sms_service._log_sms_notification(
            user_id=None,
            phone_number=user_phone,
            message=message,
            incident_id=incident_id,
            status='failed',
            error_message=str(exc)
        )
        
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

@celery.task(bind=True)
def process_incident_notification(self, incident_data):
    """
    Process incident notification by sending SMS to nearby users
    """
    try:
        if not sms_service.client or not supabase:
            logger.error("SMS service or Supabase not configured")
            return False
        
        # Get incident location
        incident_lat = incident_data.get('latitude')
        incident_lon = incident_data.get('longitude')
        
        if not incident_lat or not incident_lon:
            logger.error("Incident location not available")
            return False
        
        # Get nearby users
        nearby_users = sms_service.get_nearby_users(incident_lat, incident_lon)
        
        if not nearby_users:
            logger.info("No nearby users found for incident notification")
            return True
        
        # Create incident message
        message = sms_service._create_incident_message(incident_data)
        
        # Send SMS to all nearby users
        success_count = 0
        for user in nearby_users:
            phone = user.get('phone')
            if phone:
                # Queue individual SMS tasks
                send_sms_notification.delay(
                    incident_data.get('id'),
                    phone,
                    message
                )
                success_count += 1
        
        logger.info(f"Queued {success_count} SMS notifications for incident {incident_data.get('id')}")
        return True
        
    except Exception as exc:
        logger.error(f"Incident notification processing failed: {str(exc)}")
        raise self.retry(exc=exc, countdown=60)

@celery.task(bind=True)
def send_weather_alert(self, weather_data):
    """
    Send weather alert notifications
    """
    try:
        if not sms_service.client or not supabase:
            logger.error("SMS service or Supabase not configured")
            return False
        
        # Get all users with phone numbers
        result = supabase.table('users').select('id, phone').not_.is_('phone', 'null').execute()
        
        if not result or not result.data:
            logger.info("No users with phone numbers found for weather alert")
            return True
        
        # Create weather alert message
        message = f"""🌦️ WEATHER ALERT 🌦️

{weather_data.get('weather_alert', 'Weather Alert')}

Location: {weather_data.get('location', 'Unknown')}
Temperature: {weather_data.get('temperature', 'N/A')}°C
Condition: {weather_data.get('weather_condition', 'Unknown')}

Please take necessary precautions and stay safe.

- ResQchain Weather System"""
        
        # Send SMS to all users
        success_count = 0
        for user in result.data:
            phone = user.get('phone')
            if phone:
                send_sms_notification.delay(
                    None,  # No incident ID for weather alerts
                    phone,
                    message
                )
                success_count += 1
        
        logger.info(f"Queued {success_count} weather alert SMS notifications")
        return True
        
    except Exception as exc:
        logger.error(f"Weather alert processing failed: {str(exc)}")
        raise self.retry(exc=exc, countdown=60)

@celery.task
def check_weather_alerts():
    """
    Periodic task to check for weather alerts
    """
    try:
        if not supabase:
            logger.error("Supabase not configured")
            return False
        
        # Get recent extreme weather data
        result = supabase.table('weather_data').select('*').eq('is_extreme', True).order('created_at', desc=True).limit(10).execute()
        
        if result and result.data:
            for weather_data in result.data:
                # Check if alert was already sent
                alert_sent = supabase.table('weather_alerts_sent').select('id').eq('weather_id', weather_data['id']).execute()
                
                if not alert_sent.data:
                    # Send weather alert
                    send_weather_alert.delay(weather_data)
                    
                    # Mark as sent
                    supabase.table('weather_alerts_sent').insert({
                        'weather_id': weather_data['id'],
                        'sent_at': 'now()'
                    }).execute()
        
        return True
        
    except Exception as exc:
        logger.error(f"Weather alert check failed: {str(exc)}")
        return False

@celery.task
def cleanup_old_notifications():
    """
    Clean up old notifications and logs
    """
    try:
        if not supabase:
            logger.error("Supabase not configured")
            return False
        
        # Delete SMS notifications older than 30 days
        supabase.table('sms_notifications').delete().lt('created_at', 'now() - interval \'30 days\'').execute()
        
        # Delete weather alerts sent older than 7 days
        supabase.table('weather_alerts_sent').delete().lt('sent_at', 'now() - interval \'7 days\'').execute()
        
        logger.info("Old notifications cleaned up successfully")
        return True
        
    except Exception as exc:
        logger.error(f"Cleanup failed: {str(exc)}")
        return False

@celery.task
def send_bulk_sms(phone_numbers, message, incident_id=None):
    """
    Send bulk SMS to multiple phone numbers
    """
    try:
        if not sms_service.client:
            logger.error("SMS service not configured")
            return False
        
        success_count = 0
        for phone in phone_numbers:
            if phone:
                send_sms_notification.delay(incident_id, phone, message)
                success_count += 1
        
        logger.info(f"Queued {success_count} bulk SMS messages")
        return True
        
    except Exception as exc:
        logger.error(f"Bulk SMS failed: {str(exc)}")
        return False
