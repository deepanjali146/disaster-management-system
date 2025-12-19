"""
Optimized Weather Service for Disaster Management System
Handles fast weather data fetching and database storage
"""
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Optional
from services.weather_service import WeatherService
from repositories.weather_repo import WeatherRepository
from utils.logger import get_logger, log_exception


class OptimizedWeatherService:
    """Optimized weather service with database integration"""
    
    def __init__(self, supabase_client):
        self.weather_repo = WeatherRepository(supabase_client)
        self.logger = get_logger()
    
    def fetch_and_store_weather_data(self, app_state: dict, admin_id: str | None = None) -> Dict:
        """
        Fetch weather data for multiple locations and store in database
        Returns summary of operation
        """
        start_time = time.time()
        
        try:
            self.logger.info("Starting optimized weather data fetch and store operation")
            
            # Fetch weather data for ALL monitored locations in parallel
            monitored = WeatherService._monitored_cities()
            all_weather_results = []
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=6) as executor:
                futures = {executor.submit(WeatherService.fetch_weather_data, app_state, loc): loc for loc in monitored}
                for f in as_completed(futures):
                    try:
                        data = f.result()
                        if data:
                            all_weather_results.append(data)
                    except Exception as err:
                        log_exception(err, context=f"optimized_parallel_fetch [{futures.get(f)}]")
                        continue
            
            # Store all weather data in database
            stored_count = 0
            extreme_count = 0
            extreme_weather_locations = []

            for weather_data in all_weather_results:
                try:
                    # Prepare data for database storage
                    db_payload = self._prepare_weather_payload(weather_data)
                    
                    # Insert into database
                    weather_id = self.weather_repo.insert_weather(db_payload)
                    
                    if weather_id:
                        stored_count += 1
                        if weather_data.get('is_extreme'):
                            extreme_weather_locations.append(weather_data)
                            extreme_count += 1
                            self.logger.warning(f"Extreme weather detected: {weather_data['location']} - {weather_data.get('weather_alert')}")
                            # Auto-create announcement for extreme weather so it is visible in UI
                            try:
                                title = f"Extreme Weather Alert - {weather_data['location']}"
                                description = (
                                    f"Extreme weather detected in {weather_data['location']}. "
                                    f"Condition: {weather_data.get('weather_condition')}. "
                                    f"Temperature: {weather_data.get('temperature')}°C. "
                                )
                                if weather_data.get('weather_alert'):
                                    description += f"Alert: {weather_data.get('weather_alert')}"

                                ann_payload = {
                                    **({ 'admin_id': admin_id } if admin_id else {}),
                                    'title': title,
                                    'description': description,
                                    'is_weather_alert': True,
                                    'weather_data_id': weather_id,
                                }
                                # Optional severity heuristic
                                try:
                                    cond = (weather_data.get('weather_condition') or '').lower()
                                    if any(k in cond for k in ['thunder', 'storm', 'cyclone', 'hurricane']):
                                        ann_payload['severity'] = 'high'
                                    elif weather_data.get('temperature') and (weather_data['temperature'] > 40 or weather_data['temperature'] < -10):
                                        ann_payload['severity'] = 'high'
                                    elif weather_data.get('wind_speed') and weather_data['wind_speed'] > 20:
                                        ann_payload['severity'] = 'medium'
                                    else:
                                        ann_payload['severity'] = 'low'
                                except Exception:
                                    pass

                                # Avoid duplicates for the same weather_data_id
                                exists = None
                                try:
                                    exists = self.weather_repo.supabase.table('announcements').select('id').eq('weather_data_id', weather_id).eq('is_weather_alert', True).limit(1).execute()
                                except Exception:
                                    exists = None
                                if not exists or not exists.data:
                                    ins = self.weather_repo.supabase.table('announcements').insert(ann_payload).execute()
                                else:
                                    ins = exists
                                if not ins or not ins.data:
                                    self.logger.warning(f"Failed to auto-create announcement for {weather_data['location']}")
                            except Exception as ann_err:
                                log_exception(ann_err, context=f"create_weather_announcement [{weather_data.get('location')}]")
                    else:
                        self.logger.error(f"Failed to store weather data for {weather_data.get('location')}")
                        
                except Exception as e:
                    log_exception(e, context=f"store_weather_data [{weather_data.get('location', 'unknown')}]")
                    continue
            
            duration = time.time() - start_time
            
            result = {
                'success': True,
                'duration_seconds': round(duration, 2),
                'total_locations': len(monitored),
                'extreme_weather_found': extreme_count,
                'stored_count': stored_count,
                'extreme_count': extreme_count,
                'extreme_locations': [w['location'] for w in extreme_weather_locations if w.get('is_extreme')]
            }
            
            self.logger.info(f"Weather operation completed in {duration:.2f}s: {stored_count} stored, {extreme_count} extreme")
            return result
            
        except Exception as e:
            duration = time.time() - start_time
            log_exception(e, context="optimized_weather_fetch_and_store")
            
            return {
                'success': False,
                'duration_seconds': round(duration, 2),
                'error': str(e),
                'total_locations': len(WeatherService._monitored_cities()),
                'extreme_weather_found': 0,
                'stored_count': 0,
                'extreme_count': 0,
                'extreme_locations': []
            }
    
    def fetch_single_location_weather(self, app_state: dict, location: str) -> Optional[Dict]:
        """Fetch and store weather data for a single location"""
        try:
            # Fetch weather data
            weather_data = WeatherService.fetch_weather_data(app_state, location)
            
            if not weather_data:
                self.logger.warning(f"No weather data received for {location}")
                return None
            
            # Prepare and store data
            db_payload = self._prepare_weather_payload(weather_data)
            weather_id = self.weather_repo.insert_weather(db_payload)
            
            if weather_id:
                weather_data['id'] = weather_id
                self.logger.info(f"Weather data stored for {location} with ID: {weather_id}")
                return weather_data
            else:
                self.logger.error(f"Failed to store weather data for {location}")
                return weather_data  # Return data even if storage failed
                
        except Exception as e:
            log_exception(e, context=f"fetch_single_location_weather [{location}]")
            return None
    
    def _prepare_weather_payload(self, weather_data: Dict) -> Dict:
        """Prepare weather data for database storage"""
        return {
            'location': weather_data.get('location', 'Unknown'),
            'temperature': weather_data.get('temperature'),
            'humidity': weather_data.get('humidity'),
            'wind_speed': weather_data.get('wind_speed'),
            'weather_condition': weather_data.get('weather_condition'),
            'is_extreme': bool(weather_data.get('is_extreme', False)),
            'weather_alert': weather_data.get('weather_alert'),
            'coordinates': weather_data.get('coordinates')
        }
    
    def get_recent_weather_data(self, limit: int = 50) -> List[Dict]:
        """Get recent weather data from database"""
        try:
            result = self.weather_repo.supabase.table('weather_data').select('*').order('fetched_at', desc=True).limit(limit).execute()
            return result.data if result and result.data else []
        except Exception as e:
            log_exception(e, context="get_recent_weather_data")
            return []
    
    def get_extreme_weather_alerts(self) -> List[Dict]:
        """Get recent extreme weather alerts from database"""
        try:
            result = self.weather_repo.supabase.table('weather_data').select('*').eq('is_extreme', True).order('fetched_at', desc=True).limit(20).execute()
            return result.data if result and result.data else []
        except Exception as e:
            log_exception(e, context="get_extreme_weather_alerts")
            return []
