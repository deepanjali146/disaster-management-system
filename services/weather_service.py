from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests
from utils.logger import get_logger, log_exception


class WeatherService:
    @staticmethod
    def get_http_session(app_state):
        if 'weather' not in app_state['http_sessions']:
            retry = Retry(
                total=3,
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=frozenset(["GET"]) 
            )
            session = requests.Session()
            adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
            session.mount("http://", adapter)
            session.mount("https://", adapter)
            session.headers.update({
                "User-Agent": "DisasterManagement/1.0 (+wttr fetch)",
                "Accept": "application/json"
            })
            app_state['http_sessions']['weather'] = session
        return app_state['http_sessions']['weather']

    @staticmethod
    def fetch_weather_data(app_state, location: str):
        session = WeatherService.get_http_session(app_state)
        q = quote(location)
        weather_url = f"https://wttr.in/{q}?format=j1"
        response = session.get(weather_url, timeout=(3, 8))
        response.raise_for_status()

        # Guard against non-JSON or empty responses
        content_type = (response.headers.get("Content-Type") or "").lower()
        if "json" not in content_type:
            logger = get_logger()
            snippet = (response.text or "")[:200]
            logger.warning(f"Weather API non-JSON response for {location}: CT={content_type} body_snippet={snippet}")
            return None

        try:
            weather_data = response.json()
        except Exception as err:
            # Log JSON decode errors with a short snippet for debugging
            snippet = (response.text or "")[:200]
            log_exception(err, context=f"weather_json_decode [{location}] snippet={snippet}")
            return None
        if not weather_data:
            return None

        current_condition = (weather_data.get('current_condition') or [{}])[0]
        temp_c = current_condition.get('temp_C')
        humidity = current_condition.get('humidity')
        wind_speed = current_condition.get('windspeedKmph')
        weather_desc = (current_condition.get('weatherDesc') or [{}])[0].get('value', 'Unknown')

        temp = None
        try:
            temp = float(temp_c) if temp_c is not None else None
        except Exception:
            temp = None

        try:
            wind_val = float(wind_speed) if wind_speed is not None else None
        except Exception:
            wind_val = None

        nearest = (weather_data.get('nearest_area') or [{}])
        nearest0 = nearest[0] if nearest else {}
        lat = None
        lon = None
        try:
            lat = float((nearest0.get('latitude') or [None])[0]) if isinstance(nearest0.get('latitude'), list) else float(nearest0.get('latitude')) if nearest0.get('latitude') else None
            lon = float((nearest0.get('longitude') or [None])[0]) if isinstance(nearest0.get('longitude'), list) else float(nearest0.get('longitude')) if nearest0.get('longitude') else None
        except Exception:
            lat = None
            lon = None

        is_extreme = False
        weather_alert = None
        if temp is not None:
            if temp > 40 or temp < -10:
                is_extreme = True
                weather_alert = f"Extreme temperature: {temp}°C"
            elif temp > 35 or temp < -5:
                weather_alert = f"High temperature: {temp}°C"
        if wind_val and wind_val > 20:
            is_extreme = True
            weather_alert = f"High wind speed: {wind_val} km/h"
        severe_conditions = ['thunder', 'storm', 'tornado', 'hurricane', 'cyclone']
        if isinstance(weather_desc, str) and any(c in weather_desc.lower() for c in severe_conditions):
            is_extreme = True
            weather_alert = f"Severe weather: {weather_desc}"

        return {
            'location': location,
            'temperature': temp,
            'humidity': humidity,
            'wind_speed': wind_val,
            'weather_condition': weather_desc,
            'weather_description': weather_desc,
            'is_extreme': is_extreme,
            'weather_alert': weather_alert,
            'coordinates': {'lat': lat, 'lon': lon}
        }

    @staticmethod
    def fetch_multiple_locations_weather(app_state):
        """Optimized weather fetching for multiple locations with timeout control"""
        from_list = WeatherService._monitored_cities()
        extreme_weather_locations = []
        
        # Use fewer workers but with timeout control for faster completion
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(WeatherService.fetch_weather_data, app_state, loc): loc for loc in from_list}
            
            # Process completed futures with timeout
            completed_count = 0
            for f in as_completed(futures, timeout=8):  # 8 second total timeout
                try:
                    data = f.result()
                    completed_count += 1
                    if data and data.get('is_extreme'):
                        extreme_weather_locations.append(data)
                except Exception as err:
                    # Ensure one failure doesn't break the whole scan
                    loc = futures.get(f)
                    log_exception(err, context=f"weather_fetch_task [{loc}]")
                    continue
                    
        logger = get_logger()
        logger.info(f"Weather fetch completed: {completed_count}/{len(from_list)} cities processed")
        return extreme_weather_locations

    @staticmethod
    def _monitored_cities():
        # Optimized list of major Indian cities with simplified names for better API compatibility
        return [
            "Delhi, India", "Mumbai, India", "Kolkata, India",
            "Chennai, India", "Bangalore, India", "Hyderabad, India",
            "Ahmedabad, India", "Pune, India", "Jaipur, India",
            "Lucknow, India", "Patna, India", "Bhopal, India"
        ]


