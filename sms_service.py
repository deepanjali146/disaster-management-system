"""
SMS Notification Service using Free SMS APIs
"""
import os
import requests
import json
import time
from config import Config
from supabase import create_client, Client
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class SMSService:
    def __init__(self):
        self.supabase = None
        self.sms_enabled = False
        
        # Initialize Supabase client
        if Config.is_supabase_configured():
            self.supabase = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY)
            self.sms_enabled = True
            logger.info("Supabase client initialized for SMS logging")
        else:
            logger.warning("Supabase not configured. SMS logs will not be saved.")
        
        # Check if we have any SMS configuration
        if hasattr(Config, 'SMS_API_KEY') and Config.SMS_API_KEY:
            self.sms_enabled = True
            logger.info("SMS service initialized with free API")
        else:
            logger.info("SMS service initialized (no API key - will use mock sending)")
    
    def send_incident_notification(self, incident_data, nearby_users):
        """
        Send SMS notifications to nearby users about an incident
        """
        if not self.sms_enabled:
            logger.warning("SMS service not enabled")
            return False
        
        if not nearby_users:
            logger.info("No nearby users to notify")
            return True
        
        # Create incident message
        message = self._create_incident_message(incident_data)
        
        success_count = 0
        failed_count = 0
        
        for user in nearby_users:
            phone_number = user.get('phone')
            if not phone_number:
                logger.warning(f"User {user.get('id')} has no phone number")
                continue
            
            try:
                # Send SMS using free API or mock
                sms_id = self._send_sms(phone_number, message)
                
                # Log SMS
                self._log_sms_notification(
                    user_id=user.get('id'),
                    phone_number=phone_number,
                    message=message,
                    incident_id=incident_data.get('id'),
                    status='sent' if sms_id else 'failed',
                    twilio_sid=sms_id,
                    error_message=None if sms_id else "SMS sending failed"
                )
                
                if sms_id:
                    success_count += 1
                    logger.info(f"SMS sent to {phone_number}: {sms_id}")
                else:
                    failed_count += 1
                    logger.error(f"Failed to send SMS to {phone_number}")
                
            except Exception as e:
                logger.error(f"Failed to send SMS to {phone_number}: {str(e)}")
                
                # Log failed SMS
                self._log_sms_notification(
                    user_id=user.get('id'),
                    phone_number=phone_number,
                    message=message,
                    incident_id=incident_data.get('id'),
                    status='failed',
                    error_message=str(e)
                )
                
                failed_count += 1
        
        logger.info(f"SMS notifications sent: {success_count} successful, {failed_count} failed")
        return success_count > 0
    
    def _send_sms(self, phone_number, message):
        """
        Send SMS using free API or mock service
        """
        try:
            # Try free SMS API first (TextBelt, TextLocal, etc.)
            if hasattr(Config, 'SMS_API_KEY') and Config.SMS_API_KEY:
                return self._send_via_free_api(phone_number, message)
            else:
                # Mock SMS sending for development
                return self._send_mock_sms(phone_number, message)
        except Exception as e:
            logger.error(f"SMS sending error: {str(e)}")
            return None
    
    def _send_via_free_api(self, phone_number, message):
        """
        Send SMS using free API service
        """
        try:
            # Using TextBelt (free tier: 1 SMS per day)
            url = "https://textbelt.com/text"
            data = {
                'phone': phone_number,
                'message': message,
                'key': Config.SMS_API_KEY
            }
            
            response = requests.post(url, data=data, timeout=10)
            result = response.json()
            
            if result.get('success'):
                return f"textbelt_{result.get('textId', 'unknown')}"
            else:
                logger.error(f"TextBelt API error: {result.get('error', 'Unknown error')}")
                return None
                
        except Exception as e:
            logger.error(f"Free API SMS error: {str(e)}")
            return None
    
    def _send_mock_sms(self, phone_number, message):
        """
        Mock SMS sending for development/testing
        """
        logger.info(f"📱 MOCK SMS to {phone_number}: {message[:50]}...")
        return f"mock_{int(time.time())}"
    
    def _create_incident_message(self, incident_data):
        """
        Create a concise SMS message for incident notification
        """
        location = incident_data.get('location', 'Unknown location')
        pincode = incident_data.get('pincode', '')
        severity = incident_data.get('severity', 'medium')
        description = incident_data.get('description', 'No description available')
        
        # Truncate description if too long
        if len(description) > 80:
            description = description[:77] + "..."
        
        # Create location info
        location_info = location
        if pincode:
            location_info += f" (Pincode: {pincode})"
        
        # Create severity emoji
        severity_emoji = {
            'low': '⚠️',
            'medium': '🚨',
            'high': '🚨🚨',
            'critical': '🚨🚨🚨'
        }.get(severity.lower(), '🚨')
        
        message = f"""{severity_emoji} DISASTER WARNING {severity_emoji}

VERIFIED INCIDENT in {location_info}

Severity: {severity.upper()}
Details: {description}

⚠️ SAFETY INSTRUCTIONS:
• Stay indoors
• Avoid the area
• Follow authorities
• Keep supplies ready

This incident has been VERIFIED and forwarded to government authorities.

Stay safe!
- ResQchain Emergency System"""
        
        return message
    
    def _log_sms_notification(self, user_id, phone_number, message, incident_id, status, twilio_sid=None, error_message=None):
        """
        Log SMS notification to database
        """
        if not self.supabase:
            return
        
        try:
            log_data = {
                'user_id': user_id,
                'phone_number': phone_number,
                'message': message,
                'incident_id': incident_id,
                'status': status,
                'twilio_sid': twilio_sid,
                'error_message': error_message
            }
            
            result = self.supabase.table('sms_notifications').insert(log_data).execute()
            if result and result.data:
                logger.info(f"SMS notification logged: {result.data[0]['id']}")
            else:
                logger.error("Failed to log SMS notification")
                
        except Exception as e:
            logger.error(f"Error logging SMS notification: {str(e)}")
    
    def get_nearby_users(self, incident_lat, incident_lon, incident_pincode=None, radius_km=10):
        """
        Get users within specified radius of incident location or same pincode
        """
        if not self.supabase:
            logger.warning("Supabase not configured, returning empty user list")
            return []
        
        try:
            # Get all users with phone numbers
            result = self.supabase.table('users').select('id, phone, latitude, longitude, name, email, pincode').not_.is_('phone', 'null').execute()
            
            if not result or not result.data:
                logger.info("No users with phone numbers found in database")
                return []
            
            nearby_users = []
            pincode_users = []
            
            for user in result.data:
                user_lat = user.get('latitude')
                user_lon = user.get('longitude')
                user_pincode = user.get('pincode')
                
                # First priority: Same pincode users
                if incident_pincode and user_pincode and incident_pincode == user_pincode:
                    pincode_users.append(user)
                    logger.info(f"User {user.get('name', user.get('id'))} is in same pincode {incident_pincode}")
                    continue
                
                # Second priority: Users within radius
                if user_lat and user_lon and incident_lat and incident_lon:
                    # Calculate distance
                    distance = self._calculate_distance(incident_lat, incident_lon, user_lat, user_lon)
                    
                    if distance <= radius_km:
                        nearby_users.append(user)
                        logger.info(f"User {user.get('name', user.get('id'))} is {distance:.2f}km away from incident")
                else:
                    # If user doesn't have location, include them anyway (they might want notifications)
                    logger.info(f"User {user.get('name', user.get('id'))} has no location data, including in notifications")
                    nearby_users.append(user)
            
            # Combine pincode users (highest priority) with nearby users
            all_users = pincode_users + nearby_users
            
            # Remove duplicates based on user ID
            unique_users = []
            seen_ids = set()
            for user in all_users:
                if user.get('id') not in seen_ids:
                    unique_users.append(user)
                    seen_ids.add(user.get('id'))
            
            logger.info(f"Found {len(unique_users)} users for SMS notifications ({len(pincode_users)} same pincode, {len(nearby_users)} nearby)")
            return unique_users
            
        except Exception as e:
            logger.error(f"Error getting nearby users: {str(e)}")
            return []
    
    def _calculate_distance(self, lat1, lon1, lat2, lon2):
        """
        Calculate distance between two points in kilometers
        """
        from geopy.distance import geodesic
        return geodesic((lat1, lon1), (lat2, lon2)).kilometers

# Global SMS service instance
sms_service = SMSService()
