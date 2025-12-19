from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import quote
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests
from utils.logger import get_logger, log_exception


class EnhancedWeatherService:
    """Enhanced weather service with Indian weather standards and proper alert levels"""
    
    # Indian Weather Alert Standards (Comprehensive)
    WEATHER_ALERTS = {
        'heat_wave': {
            'yellow': {'temp': 40, 'departure': 4.5, 'description': 'Heat Wave Warning (Plains)'},
            'orange': {'temp': 45, 'departure': 6.5, 'description': 'Severe Heat Wave'},
            'red': {'temp': 47, 'days': 3, 'description': 'Extreme Heat Wave (Prolonged ≥3 days)'}
        },
        'cold_wave': {
            'yellow': {'min_temp': 10, 'departure': -4.5, 'description': 'Cold Wave Warning'},
            'orange': {'departure': -6.5, 'description': 'Severe Cold Wave'},
            'red': {'min_temp': 4, 'widespread': True, 'description': 'Widespread Extreme Cold Wave'}
        },
        'rainfall': {
            'yellow': {'min_mm': 64.5, 'max_mm': 115.5, 'description': 'Heavy Rain (24 hrs)'},
            'orange': {'min_mm': 115.6, 'max_mm': 204.4, 'description': 'Very Heavy Rain (24 hrs)'},
            'red': {'min_mm': 204.5, 'description': 'Extremely Heavy Rain (24 hrs)'}
        },
        'cyclone': {
            'yellow': {'min_wind': 62, 'max_wind': 87, 'description': 'Cyclonic Storm'},
            'orange': {'min_wind': 88, 'max_wind': 117, 'description': 'Severe Cyclonic Storm'},
            'red': {'min_wind': 118, 'description': 'Very Severe / Super Cyclone'}
        },
        'thunderstorm': {
            'yellow': {'wind': 30, 'lightning': True, 'description': 'Thunderstorm with Lightning'},
            'orange': {'wind': 50, 'hail': True, 'description': 'Severe Thunderstorm with Hail'},
            'red': {'wind': 70, 'widespread': True, 'description': 'Destructive Thunderstorm'}
        },
        'dust_sandstorm': {
            'yellow': {'wind': 30, 'visibility': 1000, 'description': 'Dust Storm'},
            'orange': {'wind': 50, 'visibility': 500, 'description': 'Severe Dust Storm'},
            'red': {'wind': 60, 'visibility': 200, 'description': 'Extreme Dust Storm'}
        },
        'cold_day': {
            'yellow': {'max_temp': 16, 'description': 'Cold Day'},
            'orange': {'max_temp': 14, 'description': 'Severe Cold Day'},
            'red': {'max_temp': 12, 'days': 2, 'description': 'Extreme Cold Day (≥2 days)'}
        },
        'drought': {
            'yellow': {'deficiency': 26, 'max_deficiency': 50, 'description': 'Moderate Drought'},
            'orange': {'deficiency': 50, 'description': 'Severe Drought'},
            'red': {'deficiency': 50, 'multi_seasonal': True, 'description': 'Multi-seasonal Drought Crisis'}
        },
        'storm_surge': {
            'yellow': {'surge': 0.5, 'max_surge': 1.0, 'description': 'Moderate Storm Surge'},
            'orange': {'surge': 1.0, 'max_surge': 2.0, 'description': 'Severe Storm Surge'},
            'red': {'surge': 2.0, 'flooding': True, 'description': 'Extreme Storm Surge with Coastal Flooding'}
        },
        'snowfall': {
            'yellow': {'snow': 2, 'max_snow': 5, 'description': 'Moderate Snowfall'},
            'orange': {'snow': 6, 'max_snow': 10, 'description': 'Heavy Snowfall'},
            'red': {'snow': 10, 'avalanche': True, 'description': 'Extreme Snowfall with Avalanche Risk'}
        },
        'forest_fire': {
            'yellow': {'temp': 30, 'max_temp': 40, 'dryness': 'moderate', 'description': 'Moderate Fire Risk'},
            'orange': {'temp': 40, 'dryness': 'high', 'description': 'High Fire Risk'},
            'red': {'temp': 42, 'dryness': 'extreme', 'winds': True, 'description': 'Extreme Fire Risk'}
        },
        'humidity_discomfort': {
            'yellow': {'heat_index': 41, 'max_index': 54, 'description': 'Heat Index Caution'},
            'orange': {'heat_index': 55, 'max_index': 65, 'description': 'Heat Index Extreme Caution'},
            'red': {'heat_index': 65, 'stress': True, 'description': 'Heat Index Danger Zone'}
        }
    }
    
    ALERT_COLORS = {
        'green': {'emoji': '🟩', 'meaning': 'No warning', 'action': 'No action needed'},
        'yellow': {'emoji': '🟨', 'meaning': 'Be updated', 'action': 'Weather could change — monitor forecasts'},
        'orange': {'emoji': '🟧', 'meaning': 'Be prepared', 'action': 'Dangerous weather expected — stay alert'},
        'red': {'emoji': '🟥', 'meaning': 'Take action', 'action': 'Extremely severe weather — emergency measures required'}
    }

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
        session = EnhancedWeatherService.get_http_session(app_state)
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
        visibility = current_condition.get('visibility')

        temp = None
        try:
            temp = float(temp_c) if temp_c is not None else None
        except Exception:
            temp = None

        try:
            wind_val = float(wind_speed) if wind_speed is not None else None
        except Exception:
            wind_val = None

        try:
            vis_val = float(visibility) if visibility is not None else None
        except Exception:
            vis_val = None

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

        # Enhanced weather analysis with Indian standards
        weather_analysis = EnhancedWeatherService.analyze_weather_conditions(
            temp, wind_val, vis_val, weather_desc, humidity
        )

        return {
            'location': location,
            'temperature': temp,
            'humidity': humidity,
            'wind_speed': wind_val,
            'visibility': vis_val,
            'weather_condition': weather_desc,
            'weather_description': weather_desc,
            'is_extreme': weather_analysis['is_extreme'],
            'weather_alert': weather_analysis['alert_message'],
            'alert_level': weather_analysis['alert_level'],
            'alert_color': weather_analysis['alert_color'],
            'alert_type': weather_analysis['alert_type'],
            'coordinates': {'lat': lat, 'lon': lon}
        }

    @staticmethod
    def analyze_weather_conditions(temp, wind_speed, visibility, weather_desc, humidity):
        """Analyze weather conditions according to comprehensive Indian weather standards"""
        alert_level = 'green'
        alert_color = 'green'
        alert_type = None
        alert_message = None
        is_extreme = False
        
        weather_desc_lower = weather_desc.lower() if weather_desc else ''
        
        # Convert string values to float for numeric comparisons
        try:
            temp = float(temp) if temp is not None else None
        except (ValueError, TypeError):
            temp = None
            
        try:
            wind_speed = float(wind_speed) if wind_speed is not None else None
        except (ValueError, TypeError):
            wind_speed = None
            
        try:
            visibility = float(visibility) if visibility is not None else None
        except (ValueError, TypeError):
            visibility = None
            
        try:
            humidity = float(humidity) if humidity is not None else None
        except (ValueError, TypeError):
            humidity = None
        
        # Heat Wave Analysis (Updated standards)
        if temp is not None:
            if temp >= 47:
                alert_level = 'red'
                alert_color = 'red'
                alert_type = 'heat_wave'
                alert_message = f"🌡️ EXTREME HEAT WAVE: {temp}°C (Prolonged ≥3 days) - Take immediate action!"
                is_extreme = True
            elif temp >= 45:
                alert_level = 'orange'
                alert_color = 'orange'
                alert_type = 'heat_wave'
                alert_message = f"🌡️ SEVERE HEAT WAVE: {temp}°C - Be prepared!"
                is_extreme = True
            elif temp >= 40:
                alert_level = 'yellow'
                alert_color = 'yellow'
                alert_type = 'heat_wave'
                alert_message = f"🌡️ Heat Wave Warning: {temp}°C (Plains) - Stay updated!"
                is_extreme = True
            elif temp <= 4:
                alert_level = 'red'
                alert_color = 'red'
                alert_type = 'cold_wave'
                alert_message = f"❄️ WIDESPREAD EXTREME COLD WAVE: {temp}°C - Take immediate action!"
                is_extreme = True
            elif temp <= 10:
                alert_level = 'yellow'
                alert_color = 'yellow'
                alert_type = 'cold_wave'
                alert_message = f"❄️ Cold Wave Warning: {temp}°C - Stay updated!"
                is_extreme = True

        # Wind Speed Analysis (Cyclone/Storm - Updated standards)
        if wind_speed is not None:
            if wind_speed >= 118:
                alert_level = 'red'
                alert_color = 'red'
                alert_type = 'cyclone'
                alert_message = f"🌪️ VERY SEVERE / SUPER CYCLONE: {wind_speed} km/h - Emergency measures required!"
                is_extreme = True
            elif wind_speed >= 88:
                alert_level = 'orange'
                alert_color = 'orange'
                alert_type = 'cyclone'
                alert_message = f"🌪️ SEVERE CYCLONIC STORM: {wind_speed} km/h - Be prepared!"
                is_extreme = True
            elif wind_speed >= 62:
                alert_level = 'yellow'
                alert_color = 'yellow'
                alert_type = 'cyclone'
                alert_message = f"🌪️ Cyclonic Storm: {wind_speed} km/h - Stay updated!"
                is_extreme = True

        # Thunderstorm Analysis (Updated standards)
        if any(word in weather_desc_lower for word in ['thunder', 'storm', 'lightning']):
            if wind_speed and wind_speed >= 70:
                alert_level = 'red'
                alert_color = 'red'
                alert_type = 'thunderstorm'
                alert_message = f"⚡ DESTRUCTIVE THUNDERSTORM: {wind_speed} km/h winds, widespread lightning - Emergency measures!"
                is_extreme = True
            elif wind_speed and wind_speed >= 50:
                alert_level = 'orange'
                alert_color = 'orange'
                alert_type = 'thunderstorm'
                alert_message = f"⚡ Severe Thunderstorm: {wind_speed} km/h winds, hail possible - Be prepared!"
                is_extreme = True
            elif wind_speed and wind_speed >= 30:
                alert_level = 'yellow'
                alert_color = 'yellow'
                alert_type = 'thunderstorm'
                alert_message = f"⚡ Thunderstorm with Lightning: {wind_speed} km/h winds - Stay updated!"
                is_extreme = True

        # Fog Analysis (Updated standards) - REMOVED
        # Fog alerts have been removed as requested
        # if visibility is not None:
        #     if visibility < 50:
        #         alert_level = 'red'
        #         alert_color = 'red'
        #         alert_type = 'fog'
        #         alert_message = f"🌫️ VERY DENSE FOG: Visibility {visibility} km - Transport disruption!"
        #         is_extreme = True
        #     elif visibility < 200:
        #         alert_level = 'orange'
        #         alert_color = 'orange'
        #         alert_type = 'fog'
        #         alert_message = f"🌫️ Dense Fog: Visibility {visibility} km - Be prepared!"
        #         is_extreme = True
        #     elif visibility < 500:
        #         alert_level = 'yellow'
        #         alert_color = 'yellow'
        #         alert_type = 'fog'
        #         alert_message = f"🌫️ Moderate Fog: Visibility {visibility} km - Stay updated!"
        #         is_extreme = True

        # Dust/Sandstorm Analysis (Updated standards)
        if any(word in weather_desc_lower for word in ['dust', 'sand', 'squall']):
            if wind_speed and wind_speed >= 60 and visibility and visibility < 200:
                alert_level = 'red'
                alert_color = 'red'
                alert_type = 'dust_sandstorm'
                alert_message = f"🌬️ EXTREME DUST STORM: {wind_speed} km/h winds, visibility {visibility} km - Emergency measures!"
                is_extreme = True
            elif wind_speed and wind_speed >= 50 and visibility and visibility < 500:
                alert_level = 'orange'
                alert_color = 'orange'
                alert_type = 'dust_sandstorm'
                alert_message = f"🌬️ Severe Dust Storm: {wind_speed} km/h winds, visibility {visibility} km - Be prepared!"
                is_extreme = True
            elif wind_speed and wind_speed >= 30 and visibility and visibility < 1000:
                alert_level = 'yellow'
                alert_color = 'yellow'
                alert_type = 'dust_sandstorm'
                alert_message = f"🌬️ Dust Storm: {wind_speed} km/h winds, visibility {visibility} km - Stay updated!"
                is_extreme = True

        # Cold Day Analysis (New)
        if temp is not None and temp <= 16:
            if temp <= 12:
                alert_level = 'red'
                alert_color = 'red'
                alert_type = 'cold_day'
                alert_message = f"🌊 EXTREME COLD DAY: {temp}°C (≥2 days) - Take immediate action!"
                is_extreme = True
            elif temp <= 14:
                alert_level = 'orange'
                alert_color = 'orange'
                alert_type = 'cold_day'
                alert_message = f"🌊 Severe Cold Day: {temp}°C - Be prepared!"
                is_extreme = True
            elif temp <= 16:
                alert_level = 'yellow'
                alert_color = 'yellow'
                alert_type = 'cold_day'
                alert_message = f"🌊 Cold Day: {temp}°C - Stay updated!"
                is_extreme = True

        # Heat Index Analysis (New)
        if temp is not None and humidity is not None:
            # Simplified heat index calculation: HI = T + 0.5 * (T - 20) * (H - 40) / 100
            heat_index = temp + 0.5 * (temp - 20) * (humidity - 40) / 100
            if heat_index >= 65:
                alert_level = 'red'
                alert_color = 'red'
                alert_type = 'humidity_discomfort'
                alert_message = f"🌡️ HEAT INDEX DANGER ZONE: {heat_index:.1f}°C - Heat stress risk!"
                is_extreme = True
            elif heat_index >= 55:
                alert_level = 'orange'
                alert_color = 'orange'
                alert_type = 'humidity_discomfort'
                alert_message = f"🌡️ Heat Index Extreme Caution: {heat_index:.1f}°C - Be prepared!"
                is_extreme = True
            elif heat_index >= 41:
                alert_level = 'yellow'
                alert_color = 'yellow'
                alert_type = 'humidity_discomfort'
                alert_message = f"🌡️ Heat Index Caution: {heat_index:.1f}°C - Stay updated!"
                is_extreme = True

        return {
            'is_extreme': is_extreme,
            'alert_level': alert_level,
            'alert_color': alert_color,
            'alert_type': alert_type,
            'alert_message': alert_message or "Normal weather conditions"
        }

    @staticmethod
    def create_weather_alert_announcement(weather_data, weather_id):
        """Create enhanced weather alert announcement with proper formatting"""
        if not weather_data.get('is_extreme'):
            return None
            
        alert_level = weather_data.get('alert_level', 'yellow')
        alert_color = weather_data.get('alert_color', 'yellow')
        alert_type = weather_data.get('alert_type', 'general')
        alert_message = weather_data.get('weather_alert', '')
        
        color_info = EnhancedWeatherService.ALERT_COLORS.get(alert_color, {})
        emoji = color_info.get('emoji', '🟨')
        meaning = color_info.get('meaning', 'Be updated')
        action = color_info.get('action', 'Monitor forecasts')
        
        # Create enhanced title and description
        title = f"{emoji} {alert_message.split(':')[0] if ':' in alert_message else 'Weather Alert'} - {weather_data['location']}"
        
        description = f"""
{emoji} **{alert_level.upper()} ALERT - {meaning.upper()}** {emoji}

📍 **Location:** {weather_data['location']}
🌡️ **Temperature:** {weather_data['temperature']}°C
💨 **Wind Speed:** {weather_data['wind_speed']} km/h
👁️ **Visibility:** {weather_data['visibility']} km
🌧️ **Condition:** {weather_data['weather_condition']}

⚠️ **ALERT DETAILS:**
{alert_message}

📋 **ACTION REQUIRED:**
{action}

🕐 **Alert Level:** {alert_level.upper()} ({alert_color.upper()})
📊 **Alert Type:** {alert_type.replace('_', ' ').title()}

Stay safe and follow official weather updates!
- ResQchain Emergency Management System
        """.strip()
        
        return {
            'title': title,
            'description': description,
            'severity': 'critical' if alert_level == 'red' else 'high' if alert_level == 'orange' else 'medium',
            'alert_level': alert_level,
            'alert_color': alert_color,
            'alert_type': alert_type
        }

    @staticmethod
    def fetch_multiple_locations_weather(app_state):
        """Optimized weather fetching for multiple locations with enhanced analysis"""
        from_list = EnhancedWeatherService._monitored_cities()
        extreme_weather_locations = []
        
        with ThreadPoolExecutor(max_workers=6) as executor:
            futures = {executor.submit(EnhancedWeatherService.fetch_weather_data, app_state, loc): loc for loc in from_list}
            
            completed_count = 0
            for f in as_completed(futures, timeout=8):
                try:
                    data = f.result()
                    completed_count += 1
                    if data and data.get('is_extreme'):
                        extreme_weather_locations.append(data)
                except Exception as err:
                    loc = futures.get(f)
                    log_exception(err, context=f"weather_fetch_task [{loc}]")
                    continue
                    
        logger = get_logger()
        logger.info(f"Weather fetch completed: {completed_count}/{len(from_list)} cities processed, {len(extreme_weather_locations)} extreme conditions found")
        return extreme_weather_locations

    @staticmethod
    def _monitored_cities():
        return [
            "Delhi, India", "Mumbai, India", "Kolkata, India",
            "Chennai, India", "Bangalore, India", "Hyderabad, India",
            "Ahmedabad, India", "Pune, India", "Jaipur, India",
            "Lucknow, India", "Patna, India", "Bhopal, India"
        ]


# Backward compatibility
class WeatherService(EnhancedWeatherService):
    """Backward compatibility wrapper"""
    pass
