from typing import Optional
from utils.logger import get_logger, log_exception


class WeatherRepository:
    def __init__(self, supabase_client):
        self.supabase = supabase_client
        self.logger = get_logger()

    def insert_weather(self, payload: dict) -> Optional[int]:
        """Insert weather data and return the ID"""
        try:
            # Ensure required fields are present
            if not payload.get('location'):
                self.logger.warning("Weather data missing location field")
                return None
                
            result = self.supabase.table('weather_data').insert(payload).execute()
            if result and result.data:
                weather_id = result.data[0].get('id')
                self.logger.info(f"Weather data inserted for {payload['location']} with ID: {weather_id}")
                return weather_id
            return None
        except Exception as e:
            log_exception(e, context=f"weather_insert [{payload.get('location', 'unknown')}]")
            return None

    def insert_weather_minimal(self, payload: dict) -> Optional[int]:
        """Insert minimal weather data with fallback"""
        try:
            # Create minimal payload with required fields
            minimal_payload = {
                'location': payload.get('location', 'Unknown'),
                'temperature': payload.get('temperature'),
                'humidity': payload.get('humidity'),
                'wind_speed': payload.get('wind_speed'),
                'weather_condition': payload.get('weather_condition', 'Unknown'),
                'is_extreme': bool(payload.get('is_extreme', False)),
                'weather_alert': payload.get('weather_alert')
            }
            
            result = self.supabase.table('weather_data').insert(minimal_payload).execute()
            if result and result.data:
                weather_id = result.data[0].get('id')
                self.logger.info(f"Minimal weather data inserted for {minimal_payload['location']} with ID: {weather_id}")
                return weather_id
            return None
        except Exception as e:
            log_exception(e, context=f"weather_insert_minimal [{payload.get('location', 'unknown')}]")
            return None


