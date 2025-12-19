def get_total_announcements_count():
    if not sb_available():
        return 0
    try:
        # Use count='exact' by selecting a small column
        resp = supabase.table('announcements').select('id', count='exact').limit(1).execute()
        return getattr(resp, 'count', None) or 0
    except Exception:
        return 0
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify
import io
import base64
import qrcode
from geopy.geocoders import Nominatim
from geopy.distance import geodesic
from supabase import create_client, Client
import overpy
import os
import time
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import Config
from sms_service import sms_service
from upi_payment_service import upi_payment_service
from tasks import process_incident_notification, send_weather_alert
from services.weather_service import WeatherService
from services.optimized_weather_service import OptimizedWeatherService
from repositories.weather_repo import WeatherRepository
from repositories.announcement_repo import AnnouncementRepository
from repositories.user_repo import UserRepository
from services.announcement_service import AnnouncementService
from services.auth_service import AuthService
from utils.error_handling import handle_errors
from services.incident_service import IncidentService
from repositories.incident_repo import IncidentRepository
from repositories.request_repo import RequestRepository
import json
from collections import defaultdict
import re
from datetime import datetime

app = Flask(__name__)
app.secret_key = Config.SECRET_KEY

# Centralized, dictionary-based application state to avoid tight coupling
APP_STATE = {
    "rate_limits": {
        "signup_attempts": {}
    },
    "http_sessions": {}
}

def consolidate_incidents_by_pincode(incidents):
    """
    Consolidate incidents by pincode and create unified descriptions
    """
    if not incidents:
        return []
    
    # Group incidents by pincode
    pincode_groups = defaultdict(list)
    for incident in incidents:
        pincode = incident.get('pincode', 'unknown')
        pincode_groups[pincode].append(incident)
    
    consolidated = []
    for pincode, group_incidents in pincode_groups.items():
        if len(group_incidents) == 1:
            # Single incident, use as is
            incident = group_incidents[0]
            incident['report_count'] = 1
            consolidated.append(incident)
        else:
            # Multiple incidents, consolidate
            main_incident = group_incidents[0].copy()  # Use first incident as base
            
            # Get all descriptions and create unified description
            descriptions = [inc.get('description', '') for inc in group_incidents if inc.get('description')]
            if descriptions:
                # Create a unified description from all reports
                unified_desc = create_unified_description(descriptions)
                main_incident['description'] = unified_desc
            
            # Update other fields
            main_incident['report_count'] = len(group_incidents)
            main_incident['severity'] = max([inc.get('severity', 'low') for inc in group_incidents], 
                                           key=lambda x: {'low': 1, 'medium': 2, 'high': 3}.get(x, 1))
            
            # Get the most recent timestamp
            timestamps = [inc.get('timestamp') for inc in group_incidents if inc.get('timestamp')]
            if timestamps:
                main_incident['timestamp'] = max(timestamps)
            
            consolidated.append(main_incident)
    
    # Sort by timestamp (most recent first)
    consolidated.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
    return consolidated

def create_unified_description(descriptions):
    """
    Create a unified description from multiple incident descriptions
    """
    if not descriptions:
        return "Multiple reports of incident in this area"
    
    # Clean and normalize descriptions
    cleaned_descriptions = []
    for desc in descriptions:
        if desc and desc.strip():
            # Remove extra whitespace and normalize
            cleaned = re.sub(r'\s+', ' ', desc.strip())
            cleaned_descriptions.append(cleaned)
    
    if not cleaned_descriptions:
        return "Multiple reports of incident in this area"
    
    if len(cleaned_descriptions) == 1:
        return cleaned_descriptions[0]
    
    # Find common words and phrases
    all_words = []
    for desc in cleaned_descriptions:
        words = re.findall(r'\b\w+\b', desc.lower())
        all_words.extend(words)
    
    # Count word frequency
    word_freq = defaultdict(int)
    for word in all_words:
        if len(word) > 3:  # Only consider meaningful words
            word_freq[word] += 1
    
    # Get most common words
    common_words = sorted(word_freq.items(), key=lambda x: x[1], reverse=True)[:5]
    
    # Create unified description
    if common_words:
        key_terms = [word for word, freq in common_words if freq > 1]
        if key_terms:
            base_desc = f"Multiple reports of incident involving: {', '.join(key_terms)}. "
        else:
            base_desc = "Multiple reports of incident in this area. "
    else:
        base_desc = "Multiple reports of incident in this area. "
    
    # Add summary of individual descriptions
    if len(cleaned_descriptions) <= 3:
        base_desc += "Reports include: " + "; ".join(cleaned_descriptions[:3])
    else:
        base_desc += f"Reports include: {cleaned_descriptions[0]} and {len(cleaned_descriptions)-1} other reports"
    
    return base_desc

# Simple rate limiting for signup (moved into APP_STATE)

# Supabase client setup
if not Config.is_supabase_configured():
    print("Warning: SUPABASE_URL or SUPABASE_KEY is not set. Set them in environment or .env file.")
    print("Database features will be disabled.")

supabase: Client = create_client(Config.SUPABASE_URL, Config.SUPABASE_KEY) if Config.is_supabase_configured() else None

# Helpers
def sb_available() -> bool:
    return supabase is not None

def require_role(required_role):
    def decorator(f):
        def decorated_function(*args, **kwargs):
            if "user" not in session:
                flash("Please sign in first!", "warning")
                return redirect(url_for("signin"))
            if session.get("user_role") != required_role:
                flash("Access denied. Insufficient permissions.", "danger")
                return redirect(url_for("dashboard"))
            return f(*args, **kwargs)
        decorated_function.__name__ = f.__name__
        return decorated_function
    return decorator

def fetch_weather_data(location):
    """Resilient weather data fetching via wttr.in using city name directly."""
    try:
        # Build a resilient session with retries once, stored in APP_STATE
        if 'weather' not in APP_STATE['http_sessions']:
            retry = Retry(
                total=3,
                backoff_factor=0.5,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=frozenset(["GET"]) 
            )
            _weather_session = requests.Session()
            adapter = HTTPAdapter(max_retries=retry, pool_connections=20, pool_maxsize=20)
            _weather_session.mount("http://", adapter)
            _weather_session.mount("https://", adapter)
            _weather_session.headers.update({
                "User-Agent": "DisasterManagement/1.0 (+wttr fetch)",
                "Accept": "application/json"
            })
            APP_STATE['http_sessions']['weather'] = _weather_session

        # Query wttr.in directly by location name (avoids geocoding failures/rate limits)
        q = quote(location)
        weather_url = f"https://wttr.in/{q}?format=j1"

        response = APP_STATE['http_sessions']['weather'].get(weather_url, timeout=(3, 8))
        response.raise_for_status()
        weather_data = response.json()

        if not weather_data:
            return None

        # Extract weather information from wttr.in response
        current_condition = (weather_data.get('current_condition') or [{}])[0]
        temp_c = current_condition.get('temp_C')
        humidity = current_condition.get('humidity')
        wind_speed = current_condition.get('windspeedKmph')
        weather_desc = (current_condition.get('weatherDesc') or [{}])[0].get('value', 'Unknown')

        # Optional coordinates from nearest_area, if present
        nearest = (weather_data.get('nearest_area') or [{}])
        nearest0 = nearest[0] if nearest else {}
        lat_str = (nearest0.get('latitude') or [None])
        lon_str = (nearest0.get('longitude') or [None])
        try:
            lat = float(lat_str if isinstance(lat_str, str) else (lat_str[0] if lat_str else None)) if lat_str else None
            lon = float(lon_str if isinstance(lon_str, str) else (lon_str[0] if lon_str else None)) if lon_str else None
        except Exception:
            lat = None
            lon = None

        # Convert to numeric values
        temp = float(temp_c) if temp_c not in (None, "") else None
        humidity = int(humidity) if humidity not in (None, "") else None
        wind_speed = float(wind_speed) if wind_speed not in (None, "") else None

        # Determine if weather is extreme
        is_extreme = False
        weather_alert = None

        if temp is not None:
            if temp > 40 or temp < -10:
                is_extreme = True
                weather_alert = f"Extreme temperature: {temp}°C"
            elif temp > 35 or temp < -5:
                weather_alert = f"High temperature: {temp}°C"

        try:
            wind_val = float(wind_speed) if wind_speed is not None else None
        except Exception:
            wind_val = None
        if wind_val and wind_val > 20:
            is_extreme = True
            weather_alert = f"High wind speed: {wind_val} km/h"

        severe_conditions = ['thunder', 'storm', 'tornado', 'hurricane', 'cyclone']
        if isinstance(weather_desc, str) and any(condition in weather_desc.lower() for condition in severe_conditions):
            is_extreme = True
            weather_alert = f"Severe weather: {weather_desc}"
        
        return {
            'location': location,
            'temperature': temp,
            'humidity': humidity,
            'wind_speed': wind_speed,
            'weather_condition': weather_desc,
            'weather_description': weather_desc,
            'is_extreme': is_extreme,
            'weather_alert': weather_alert,
            'coordinates': {'lat': lat, 'lon': lon}
        }

    except Exception as e:
        print(f"Error fetching weather data: {e}")
        return None

def fetch_multiple_locations_weather():
    """Ultra-fast weather data fetching for major Indian cities using optimized parallel processing"""
    # Expanded list of major Indian cities covering all regions
    locations = [
        # Northern India
        "Delhi, India",
        "Jaipur, Rajasthan, India",
        "Lucknow, Uttar Pradesh, India",
        "Chandigarh, India",
        "Dehradun, Uttarakhand, India",
        "Amritsar, Punjab, India",
        "Jammu, Jammu and Kashmir, India",
        "Srinagar, Jammu and Kashmir, India",
        "Shimla, Himachal Pradesh, India",
        
        # Western India
        "Mumbai, Maharashtra, India",
        "Pune, Maharashtra, India",
        "Nagpur, Maharashtra, India",
        "Ahmedabad, Gujarat, India",
        "Surat, Gujarat, India",
        "Vadodara, Gujarat, India",
        "Bhopal, Madhya Pradesh, India",
        "Indore, Madhya Pradesh, India",
        "Jodhpur, Rajasthan, India",
        "Udaipur, Rajasthan, India",
        "Goa, India",
        
        # Southern India
        "Bangalore, Karnataka, India",
        "Mysore, Karnataka, India",
        "Hyderabad, Telangana, India",
        "Chennai, Tamil Nadu, India",
        "Coimbatore, Tamil Nadu, India",
        "Madurai, Tamil Nadu, India",
        "Kochi, Kerala, India",
        "Thiruvananthapuram, Kerala, India",
        "Visakhapatnam, Andhra Pradesh, India",
        "Vijayawada, Andhra Pradesh, India",
        "Pondicherry, India",
        
        # Eastern India
        "Kolkata, West Bengal, India",
        "Howrah, West Bengal, India",
        "Patna, Bihar, India",
        "Ranchi, Jharkhand, India",
        "Bhubaneswar, Odisha, India",
        "Cuttack, Odisha, India",
        "Guwahati, Assam, India",
        "Shillong, Meghalaya, India",
        "Imphal, Manipur, India",
        "Agartala, Tripura, India",
        "Kohima, Nagaland, India",
        
        # Central India
        "Raipur, Chhattisgarh, India",
        "Bilaspur, Chhattisgarh, India",
        "Jabalpur, Madhya Pradesh, India",
        "Gwalior, Madhya Pradesh, India"
    ]
    
    print(f"🚀 Starting ultra-fast parallel weather fetch for {len(locations)} major Indian cities...")
    start_time = time.time()
    
    # Use ThreadPoolExecutor for parallel processing
    extreme_weather_locations = []
    successful_fetches = 0
    
    with ThreadPoolExecutor(max_workers=10) as executor:  # Increased workers for more cities
        # Submit all weather fetch tasks
        future_to_location = {executor.submit(fetch_weather_data, location): location for location in locations}
        
        # Process completed tasks
        for future in as_completed(future_to_location):
            location = future_to_location[future]
            try:
                weather_data = future.result()
                if weather_data:
                    successful_fetches += 1
                    if weather_data['is_extreme']:
                        extreme_weather_locations.append(weather_data)
                        print(f"⚠ Extreme weather in {location}: {weather_data['weather_alert']}")
                    else:
                        print(f"✅ Normal weather in {location}")
                else:
                    print(f"❌ Failed to fetch weather for {location}")
            except Exception as e:
                print(f"Error fetching weather for {location}: {e}")
    
    end_time = time.time()
    duration = end_time - start_time
    
    print(f"⚡ Weather fetch completed in {duration:.2f} seconds!")
    print(f"📊 Results: {successful_fetches}/{len(locations)} successful, {len(extreme_weather_locations)} extreme weather events found")
    
    return extreme_weather_locations

def save_weather_data(weather_data):
    """Save weather data to database with enhanced location details and create announcement when extreme.
    Returns the weather_data id if inserted, or None. Announcement creation is triggered inside for extreme cases.
    """
    if not sb_available() or not weather_data:
        return None
    
    try:
        # Extract pincode from location if available
        location = weather_data['location']
        pincode = None
        
        # Try to extract pincode from location string
        import re
        pincode_match = re.search(r'\b(\d{6})\b', location)
        if pincode_match:
            pincode = pincode_match.group(1)
        
        # Coerce numeric fields safely
        temperature = weather_data.get('temperature')
        humidity = weather_data.get('humidity')
        wind_speed = weather_data.get('wind_speed')
        try:
            temperature = float(temperature) if temperature is not None else None
        except Exception:
            temperature = None
        try:
            humidity = int(humidity) if humidity is not None else None
        except Exception:
            humidity = None
        try:
            wind_speed = float(wind_speed) if wind_speed is not None else None
        except Exception:
            wind_speed = None

        payload = {
            'location': location,
            'pincode': pincode,
            'temperature': temperature,
            'humidity': humidity,
            'wind_speed': wind_speed,
            'weather_condition': weather_data.get('weather_condition'),
            'is_extreme': bool(weather_data.get('is_extreme')),
            'weather_alert': weather_data.get('weather_alert'),
            'coordinates': weather_data.get('coordinates') or None
            # fetched_at uses DEFAULT now()
        }
        
        # Ensure we receive the inserted row back for ID
        try:
            result = supabase.table('weather_data').insert(payload).select('id').execute()
        except Exception as e:
            # Retry with minimal payload for schema compatibility
            try:
                result = supabase.table('weather_data').insert({
                    'location': location,
                    'temperature': temperature,
                    'humidity': humidity,
                    'wind_speed': wind_speed,
                    'weather_condition': weather_data.get('weather_condition'),
                    'is_extreme': bool(weather_data.get('is_extreme')),
                    'weather_alert': weather_data.get('weather_alert')
                }).select('id').execute()
            except Exception as e2:
                result = None

        if result and result.data:
            weather_id = result.data[0].get('id')
            # If extreme weather detected, automatically create an announcement
            if weather_data['is_extreme']:
                create_weather_alert_announcement(weather_data, weather_id)
            return weather_id
        else:
            # As a fallback, try to fetch the most recent record for this location
            try:
                last = supabase.table('weather_data').select('id').eq('location', location).order('id', desc=True).limit(1).execute()
                if last and last.data:
                    weather_id = last.data[0].get('id')
                    if weather_data['is_extreme']:
                        create_weather_alert_announcement(weather_data, weather_id)
                    return weather_id
            except Exception:
                pass
            # If we still couldn't persist a weather_data row, still create announcement for extreme cases
            if weather_data.get('is_extreme'):
                create_weather_alert_announcement(weather_data, None)
            return None
            return None
        
    except Exception as e:
        print(f"Error saving weather data: {e}")
        return None

def create_weather_alert_announcement(weather_data, weather_id):
    """Automatically create or update an enhanced weather alert announcement"""
    if not sb_available():
        return None
    
    try:
        from services.enhanced_weather_service import EnhancedWeatherService
        
        # Use enhanced weather service to create proper alert
        alert_data = EnhancedWeatherService.create_weather_alert_announcement(weather_data, weather_id)
        if not alert_data:
            return None
        
        # Get admin user ID
        admin_id = session.get("user_id") if session.get("user_role") == "admin" else None
        if not admin_id:
            admin_resp = supabase.table("users").select("id").eq("role", "admin").limit(1).execute()
            admin_id = admin_resp.data[0]['id'] if admin_resp and admin_resp.data else None
        
        # Check if there's already an active weather alert for this location
        location = weather_data.get('location', '')
        # Extract city name from location (e.g., "Delhi, India" -> "Delhi")
        city_name = location.split(',')[0].strip() if ',' in location else location
        
        # Search for existing weather alerts for this city
        existing_alert_resp = supabase.table("announcements").select("id, title, description").eq("is_weather_alert", True).ilike("title", f"%{city_name}%").execute()
        
        if existing_alert_resp and existing_alert_resp.data:
            # Update existing announcement instead of creating new one
            existing_alert = existing_alert_resp.data[0]
            update_payload = {
                "title": alert_data['title'],
                "description": alert_data['description'],
                "severity": alert_data['severity'],
                "weather_data_id": weather_id if weather_id else None
            }
            
            update_result = supabase.table("announcements").update(update_payload).eq("id", existing_alert['id']).execute()
            
            if update_result and update_result.data:
                print(f"Updated existing weather alert for {city_name} - Level: {alert_data['alert_level']}")
                return existing_alert['id']
        else:
            # Create new announcement if none exists for this location
            payload = {
                "title": alert_data['title'],
                "description": alert_data['description'],
                "severity": alert_data['severity'],
                "is_weather_alert": True,
                "weather_data_id": weather_id if weather_id else None
            }
            
            if admin_id:
                payload["admin_id"] = admin_id
            
            ann_result = supabase.table("announcements").insert(payload).execute()
            if ann_result and ann_result.data:
                print(f"Created new weather alert announcement for {city_name} - Level: {alert_data['alert_level']}")
                return ann_result.data[0]['id']
        
        return None
        
    except Exception as e:
        print(f"Error creating/updating weather alert announcement: {e}")
        return None

def check_and_update_weather_alerts():
    """Check existing weather alerts and remove them if weather has returned to normal"""
    if not sb_available():
        return
    
    try:
        # Get all weather alert announcements with joined weather_data (PostgREST embedded)
        ann_resp = supabase.table("announcements").select("id, title, description, weather_data_id, weather_data(*)").eq("is_weather_alert", True).execute()
        weather_alerts = ann_resp.data if ann_resp and ann_resp.data else []
        
        if not weather_alerts:
            return
        
        # Use ThreadPoolExecutor for parallel checking
        with ThreadPoolExecutor(max_workers=5) as executor:
            def check_single_alert(alert):
                # Determine location from joined weather_data or title fallback
                location = None
                if alert.get('weather_data_id') and alert.get('weather_data'):
                    location = (alert['weather_data'] or {}).get('location')
                if not location:
                    title = alert.get('title') or ''
                    # Handle both old and new title formats (fog markers removed)
                    for marker in ['Extreme Weather Alert - ', '🌡️', '❄️', '🌪️', '⚡', '🌬️']:
                        if marker in title:
                            location = title.split(marker, 1)[1].strip()
                            break
                if not location:
                    return False

                # Fetch current weather for this location via enhanced service
                from services.enhanced_weather_service import EnhancedWeatherService
                current_weather = EnhancedWeatherService.fetch_weather_data(APP_STATE, location)
                
                if current_weather:
                    if not current_weather.get('is_extreme'):
                        # Weather has returned to normal, remove the alert
                        try:
                            supabase.table("announcements").delete().eq("id", alert['id']).execute()
                            print(f"Removed weather alert for {location} - weather returned to normal")
                            return True
                        except Exception as e:
                            print(f"Error removing weather alert for {location}: {e}")
                    else:
                        # Weather is still extreme, update the existing alert with current data
                        try:
                            alert_data = EnhancedWeatherService.create_weather_alert_announcement(current_weather, alert.get('weather_data_id'))
                            if alert_data:
                                update_payload = {
                                    "title": alert_data['title'],
                                    "description": alert_data['description'],
                                    "severity": alert_data['severity'],
                                    "weather_data_id": alert.get('weather_data_id')
                                }
                                supabase.table("announcements").update(update_payload).eq("id", alert['id']).execute()
                                print(f"Updated weather alert for {location} - Level: {alert_data['alert_level']}")
                        except Exception as e:
                            print(f"Error updating weather alert for {location}: {e}")
                
                return False
            
            # Submit all alert checking tasks
            futures = [executor.submit(check_single_alert, alert) for alert in weather_alerts]
            
            # Wait for all to complete
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as e:
                    print(f"Error in alert checking: {e}")
        
    except Exception as e:
        print(f"Error checking weather alerts: {e}")

def delete_announcement(announcement_id):
    """Delete an announcement by ID"""
    if not sb_available():
        return False
    
    try:
        supabase.table("announcements").delete().eq("id", announcement_id).execute()
        return True
    except Exception as e:
        print(f"Error deleting announcement: {e}")
        return False

# Removed POST /delete_announcement (conflicted); using /delete_announcement/<id> route below

@app.route("/edit_announcement", methods=["POST"])
@require_role("admin")
def edit_announcement_route():
    ann_id = request.form.get("id")
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    if not ann_id or not title or not description:
        flash("All fields are required", "danger")
        return redirect(url_for("admin_dashboard"))
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("admin_dashboard"))
    try:
        supabase.table("announcements").update({
            "title": title,
            "description": description,
            "timestamp": datetime.now().isoformat()
        }).eq("id", int(ann_id)).execute()
        flash("Announcement updated.", "success")
    except Exception as err:
        flash(f"Error updating announcement: {err}", "danger")
    return redirect(url_for("admin_dashboard"))

def delete_incident(incident_id):
    """Delete an incident by ID"""
    if not sb_available():
        return False
    
    try:
        supabase.table("incidents").delete().eq("id", incident_id).execute()
        return True
    except Exception as e:
        print(f"Error deleting incident: {e}")
        return False

# Routes
@app.route("/")
def home():
    return render_template("home.html")

@app.route("/signup", methods=["GET", "POST"])
@handle_errors("signup", "Signup failed:")
def signup():
    if "user" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        # Simple rate limiting check via centralized APP_STATE
        client_ip = request.remote_addr
        current_time = time.time()
        signup_attempts = APP_STATE["rate_limits"]["signup_attempts"]
        if client_ip in signup_attempts:
            last_attempt = signup_attempts[client_ip]
            if current_time - last_attempt < 60:  # 60 seconds cooldown
                remaining_time = int(60 - (current_time - last_attempt))
                flash(f"Too many signup attempts. Please wait {remaining_time} seconds before trying again.", "warning")
                return redirect(url_for("signup"))
        signup_attempts[client_ip] = current_time
        
        name = request.form["fullname"].strip()
        email = request.form["email"].strip().lower()
        phone = request.form["phone"].strip()
        place = request.form.get("place", "").strip()
        city = request.form.get("city", "").strip()
        state = request.form.get("state", "").strip()
        pincode = request.form.get("pincode", "").strip()
        password = request.form["password"]
        role = request.form.get("role", "user")  # Default to user role
        
        if not sb_available():
            flash("Database is not configured.", "danger")
            return redirect(url_for("signup"))

        # Use AuthService + UserRepository
        try:
            user_repo = UserRepository(supabase)
            auth_service = AuthService(supabase, user_repo)
            user_id = auth_service.signup(name, email, phone, password, place, city, state, pincode, role)
            if not user_id:
                flash("Could not create account. Please try again.", "danger")
                return redirect(url_for("signup"))
            flash("Signup successful! Please log in.", "success")
        except Exception as err:
            error_msg = str(err)
            if "rate limit" in error_msg.lower() or "security purposes" in error_msg.lower():
                flash("Too many signup attempts. Please wait 1 minute before trying again.", "warning")
            elif "already registered" in error_msg.lower():
                flash("This email is already registered. Please sign in instead.", "info")
            else:
                flash("Signup failed. Please try again later.", "danger")
        
        return redirect(url_for("signin"))

    return render_template("signup.html")

@app.route("/view_data")
def view_data():
    if "user" not in session:
        flash("Please sign in first!", "warning")
        return redirect(url_for("signin"))

    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("dashboard"))

    data_type = request.args.get("type", "incidents").lower()
    user_id = session.get("user_id")
    rows = []
    columns = []

    try:
        if data_type == "donations":
            resp = supabase.table("donations").select("id, amount, method, timestamp").eq("user_id", user_id).order("timestamp", desc=True).execute()
            rows = resp.data if resp and resp.data else []
            columns = ["id", "amount", "method", "timestamp"]
        else:
            resp = supabase.table("incidents").select("id, location, description, status, timestamp").eq("user_id", user_id).order("timestamp", desc=True).execute()
            rows = resp.data if resp and resp.data else []
            columns = ["id", "location", "description", "status", "timestamp"]
    except Exception as err:
        flash(f"Error fetching data: {err}", "danger")
        return redirect(url_for("dashboard"))

    return render_template("view_data.html", data_type=data_type, columns=columns, rows=rows)

@app.route("/signin", methods=["GET", "POST"])
@handle_errors("signin", "Sign in failed:")
def signin():
    if "user" in session:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email_or_phone = request.form["email_or_phone"].strip()
        password = request.form["password"]

        if not sb_available():
            flash("Database is not configured.", "danger")
            return redirect(url_for("signin"))

        # Use AuthService and UserRepository
        try:
            user_repo = UserRepository(supabase)
            auth_service = AuthService(supabase, user_repo)
            res = auth_service.signin(email_or_phone, password)
            if not res:
                flash("Invalid credentials or user not found", "danger")
                return redirect(url_for("signin"))
            user_id = res["user_id"]
            profile = res["profile"] or {}
            first_name = (profile.get("name") or "").split()[0] or "User"
            user_role = profile.get("role", "user")
            session["user"] = first_name
            session["user_id"] = user_id
            session["user_email"] = profile.get("email")
            session["user_role"] = user_role
            flash("Signed in successfully!", "success")
            return redirect(url_for("dashboard"))
        except Exception as err:
            flash(f"Sign in error: {err}", "danger")
            return redirect(url_for("signin"))

    return render_template("signin.html")

@app.route("/dashboard")
def dashboard():
    if "user" not in session:
        flash("Please sign in first!", "warning")
        return redirect(url_for("signin"))
    
    user_role = session.get("user_role", "user")
    
    if user_role == "admin":
        return redirect(url_for("admin_dashboard"))
    elif user_role == "government":
        return redirect(url_for("government_dashboard"))
    elif user_role == "emergency":
        return redirect(url_for("emergency_dashboard"))
    else:
        # Get recent announcements for user dashboard
        announcements = []
        weather_alerts = []
        if sb_available():
            try:
                # Check and update weather alerts (remove resolved ones)
                check_and_update_weather_alerts()
                
                # Get all recent announcements
                ann_resp = supabase.table("announcements").select("*, weather_data!announcements_weather_data_id_fkey(*)").order("timestamp", desc=True).limit(5).execute()
                announcements = ann_resp.data if ann_resp and ann_resp.data else []
                
                # Filter weather alerts
                weather_alerts = [ann for ann in announcements if ann.get('is_weather_alert')]
            except Exception as err:
                print(f"Error loading announcements: {err}")
        
        return render_template("dashboard.html", user=session["user"], announcements=announcements, weather_alerts=weather_alerts)

@app.route("/admin_dashboard")
@require_role("admin")
def admin_dashboard():
    # Get incidents for admin to review
    incidents = []
    announcements = []
    admin_operations = []
    weather_data = []
    total_incidents = 0
    forwarded_incidents = 0
    total_donations = 0
    total_amount = 0
    sms_configured = False
    
    if sb_available():
        try:
            # Check and update weather alerts (remove resolved ones)
            check_and_update_weather_alerts()
            
            # Get all incidents
            inc_resp = supabase.table("incidents").select("*").order("timestamp", desc=True).execute()
            all_incidents = inc_resp.data if inc_resp and inc_resp.data else []
            
            # Separate pending and forwarded incidents
            pending_incidents = [i for i in all_incidents if i.get('status') != 'forwarded']
            forwarded_incidents = [i for i in all_incidents if i.get('status') == 'forwarded']
            
            # Consolidate incidents by pincode via service (same behavior)
            pending_incidents = IncidentService.consolidate_by_pincode(pending_incidents)
            forwarded_incidents = IncidentService.consolidate_by_pincode(forwarded_incidents)
            
            # Get statistics
            total_incidents = len(all_incidents)
            forwarded_count = len([i for i in all_incidents if i.get('status') == 'forwarded'])
            
            # Get donation statistics (include verified, completed, success, paid)
            try:
                donations_resp = supabase.table("donations").select("*").execute()
                donations = donations_resp.data if donations_resp and donations_resp.data else []
                ok_status = ['verified','completed','success','paid']
                total_donations = len([d for d in donations if (d.get('status') or '').lower() in ok_status])
                total_amount = sum(float(d.get('amount', 0) or 0) for d in donations if (d.get('status') or '').lower() in ok_status)
            except:
                pass
            
            ann_resp = supabase.table("announcements").select("*").order("timestamp", desc=True).limit(10).execute()
            announcements = ann_resp.data if ann_resp and ann_resp.data else []
            
            # Build admin operations overview from assignments + updates (more robust)
            try:
                asg_resp = supabase.table("emergency_assignments").select(
                    "id, request_id, team_lead_id, unit_id, status, assigned_at, completed_at, team_name, team_type, location_text, requests(incident_id, incidents(*))"
                ).order("assigned_at", desc=True).limit(50).execute()
                assignments = asg_resp.data if asg_resp and asg_resp.data else []

                # Collect IDs for lookups
                lead_ids = {a.get('team_lead_id') for a in assignments if a.get('team_lead_id')}
                unit_ids = {a.get('unit_id') for a in assignments if a.get('unit_id')}
                asg_ids = [a.get('id') for a in assignments if a.get('id')]

                users_map = {}
                units_map = {}
                updates_by_asg = {}

                if lead_ids:
                    try:
                        uresp = supabase.table("users").select("id, name").in_("id", list(lead_ids)).execute()
                        for u in (uresp.data or []):
                            users_map[u.get('id')] = u
                    except Exception:
                        pass
                if unit_ids:
                    try:
                        unresp = supabase.table("emergency_units").select("id, unit_name, unit_category").in_("id", list(unit_ids)).execute()
                        for un in (unresp.data or []):
                            units_map[un.get('id')] = un
                    except Exception:
                        pass
                if asg_ids:
                    try:
                        upresp = supabase.table("emergency_updates").select("assignment_id, rescued_count, created_at").in_("assignment_id", asg_ids).execute()
                        for up in (upresp.data or []):
                            aid = up.get('assignment_id')
                            if aid not in updates_by_asg:
                                updates_by_asg[aid] = {"rescued": 0, "last": up.get('created_at')}
                            rescued_val = int(up.get('rescued_count') or 0)
                            updates_by_asg[aid]["rescued"] += rescued_val
                            # track latest time
                            t = up.get('created_at')
                            if t and (not updates_by_asg[aid]["last"] or t > updates_by_asg[aid]["last"]):
                                updates_by_asg[aid]["last"] = t
                    except Exception:
                        pass

                # Build admin_operations list
                for a in assignments:
                    inc = (a.get('requests') or {}).get('incidents') or {}
                    lead = users_map.get(a.get('team_lead_id')) or {}
                    unit = units_map.get(a.get('unit_id')) or {}
                    sums = updates_by_asg.get(a.get('id')) or {"rescued": 0, "last": a.get('assigned_at')}
                    admin_operations.append({
                        "assignment_id": a.get('id'),
                        "incident_id": (a.get('requests') or {}).get('incident_id'),
                        "incident_location": inc.get('location') or a.get('location_text'),
                        "team": unit.get('unit_name') or lead.get('name') or a.get('team_name') or 'Emergency Team',
                        "team_type": unit.get('unit_category') or a.get('team_type'),
                        "status": a.get('status') or 'Assigned',
                        "rescued": sums.get('rescued', 0),
                        "updated_at": sums.get('last')
                    })
            except Exception:
                admin_operations = []

            # Admin emergency updates (mirror of government view)
            admin_updates = []
            try:
                updates_resp = supabase.table("government_emergency_updates").select(
                    "update_id, assignment_id, team_name, assignment_status, rescued_count, critical_count, severity, message, update_time, location, city, state"
                ).limit(20).execute()
                admin_updates = updates_resp.data if updates_resp and updates_resp.data else []
            except Exception:
                admin_updates = []

            # Get recent weather data, prioritizing extreme weather and most recent
            weather_resp = supabase.table("weather_data").select("*").order("fetched_at", desc=True).order("is_extreme", desc=True).limit(15).execute()
            weather_data = weather_resp.data if weather_resp and weather_resp.data else []
            
            # Check SMS configuration
            sms_configured = Config.is_sms_configured()
            
        except Exception as err:
            flash(f"Error loading data: {err}", "danger")
    
    return render_template("admin_dashboard.html", 
                         pending_incidents=pending_incidents,
                         forwarded_incidents=forwarded_incidents,
                         announcements=announcements, 
                         admin_operations=admin_operations,
                         admin_updates=admin_updates,
                         weather_data=weather_data,
                         total_incidents=total_incidents,
                         forwarded_incidents_count=forwarded_count,
                         total_donations=total_donations,
                         total_amount=total_amount,
                         sms_configured=sms_configured)

@app.route("/fetch_weather", methods=["POST"])
@require_role("admin")
def fetch_weather():
    """Fetch weather data for a location using optimized service"""
    location = request.form.get("location")
    
    if not location:
        flash("Location is required", "danger")
        return redirect(url_for("admin_dashboard"))
    
    # Use optimized weather service
    optimized_service = OptimizedWeatherService(supabase)
    weather_data = optimized_service.fetch_single_location_weather(APP_STATE, location)
    
    if weather_data:
        if weather_data.get('id'):
            flash(f"Weather data fetched and stored for {location} successfully!", "success")
        else:
            flash("Weather data fetched but could not save to database", "warning")
    else:
        flash(f"Could not fetch weather data for {location}", "danger")
    
    return redirect(url_for("admin_dashboard"))

@app.route("/fetch_extreme_weather", methods=["POST"])
@require_role("admin")
@handle_errors("admin_dashboard", "Weather scan failed:")
def fetch_extreme_weather():
    """Fetch weather data for multiple Indian cities using enhanced service"""
    flash("Fetching weather data for all monitored Indian cities...", "info")
    
    try:
        from services.enhanced_weather_service import EnhancedWeatherService
        
        # Fetch weather for multiple locations using enhanced service
        extreme_weather_locations = EnhancedWeatherService.fetch_multiple_locations_weather(APP_STATE)
        
        alerts_created = 0
        stored_count = 0
        
        for weather_data in extreme_weather_locations:
            # Save weather data to database
            weather_id = save_weather_data(weather_data)
            if weather_id:
                stored_count += 1
                
                # Create weather alert announcement
                announcement_id = create_weather_alert_announcement(weather_data, weather_id)
                if announcement_id:
                    alerts_created += 1
        
        if alerts_created > 0:
            flash(f"Enhanced weather scan completed! Found {alerts_created} extreme weather events requiring alerts. {stored_count} weather records saved.", "success")
        else:
            flash(f"Enhanced weather scan completed! No extreme weather detected. {stored_count} weather records saved.", "info")
            
    except Exception as err:
        flash(f"Weather scan failed: {err}", "danger")
    
    return redirect(url_for("admin_dashboard"))

@app.route("/check_weather_alerts", methods=["POST"])
@require_role("admin")
@handle_errors("admin_dashboard", "Weather alert check failed:")
def check_weather_alerts():
    """Check and update weather alerts - remove alerts where weather has returned to normal"""
    flash("Checking weather alerts and removing resolved ones...", "info")
    
    check_and_update_weather_alerts()
    
    flash("Weather alert check completed!", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/delete_announcement/<int:announcement_id>", methods=["POST"])
@require_role("admin")
@handle_errors("admin_dashboard", "Delete announcement failed:")
def delete_announcement_route(announcement_id):
    """Delete an announcement"""
    if delete_announcement(announcement_id):
        flash("Announcement deleted successfully!", "success")
    else:
        flash("Failed to delete announcement.", "danger")
    
    return redirect(url_for("admin_dashboard"))

@app.route("/edit_announcement", methods=["POST"], endpoint="edit_announcement")
@require_role("admin")
@handle_errors("admin_dashboard", "Edit announcement failed:")
def edit_announcement_post():
    """Edit an announcement's title and description."""
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("admin_dashboard"))

    ann_id = request.form.get("id")
    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()

    if not ann_id:
        flash("Announcement id is required.", "danger")
        return redirect(url_for("admin_dashboard"))

    try:
        update_payload = {}
        if title:
            update_payload["title"] = title
        if description:
            update_payload["description"] = description

        if not update_payload:
            flash("Nothing to update.", "info")
            return redirect(url_for("admin_dashboard"))

        resp = supabase.table("announcements").update(update_payload).eq("id", int(ann_id)).execute()
        if not resp or not resp.data:
            flash("Failed to update announcement.", "danger")
        else:
            flash("Announcement updated successfully!", "success")
    except Exception as err:
        flash(f"Edit failed: {err}", "danger")

    return redirect(url_for("admin_dashboard"))

@app.route("/delete_incident/<int:incident_id>", methods=["POST"])
@require_role("admin")
def delete_incident_route(incident_id):
    """Delete an incident"""
    if delete_incident(incident_id):
        flash("Incident deleted successfully!", "success")
    else:
        flash("Failed to delete incident.", "danger")
    
    return redirect(url_for("admin_dashboard"))

@app.route("/government_dashboard")
@require_role("government")
def government_dashboard():
    # Get requests for government to handle
    requests = []
    pending_requests_list = []
    notified_requests_list = []
    team_allocations = []
    emergency_assignments = []
    emergency_heads = []
    emergency_units = []
    emergency_updates = []
    total_requests = 0
    pending_requests = 0
    active_assignments = 0
    completed_tasks = 0

    if sb_available():
        try:
            # Requests for government (split by status)
            req_pending = supabase.table("requests").select(
                "id, incident_id, status, timestamp, incidents(*)"
            ).eq("status", "pending").order("timestamp", desc=True).limit(50).execute()
            pending_requests_list = req_pending.data if req_pending and req_pending.data else []

            req_notified = supabase.table("requests").select(
                "id, incident_id, status, timestamp, incidents(*)"
            ).eq("status", "notified").order("timestamp", desc=True).limit(50).execute()
            notified_requests_list = req_notified.data if req_notified and req_notified.data else []

            # Aggregate pending and notified requests by pincode to avoid duplicates
            def group_requests_by_pincode(req_list):
                grouped = {}
                for r in req_list or []:
                    incident = r.get('incidents') or {}
                    pincode = (incident.get('pincode') or 'unknown')
                    key = f"{pincode}:{incident.get('location') or ''}:{incident.get('severity') or ''}"
                    if key not in grouped:
                        grouped[key] = {
                            **r,
                            'request_count': 1
                        }
                    else:
                        grouped[key]['request_count'] += 1
                        # Keep most recent timestamp
                        try:
                            if (r.get('timestamp') or '') > (grouped[key].get('timestamp') or ''):
                                grouped[key]['timestamp'] = r.get('timestamp')
                        except Exception:
                            pass
                # Return list of representative requests with counts
                return sorted(grouped.values(), key=lambda x: x.get('timestamp') or '', reverse=True)

            pending_requests_list = group_requests_by_pincode(pending_requests_list)
            notified_requests_list = group_requests_by_pincode(notified_requests_list)

            # Keep 'requests' as union for modals/compat if needed
            requests = (pending_requests_list or []) + (notified_requests_list or [])
            
            # Get statistics
            total_requests = len(requests)
            pending_requests = len(pending_requests_list)
            completed_tasks = len([r for r in requests if r.get('status') == 'completed'])
            
            # Team allocations
            team_resp = supabase.table("team_allocations").select("*").order(
                "assigned_at", desc=True
            ).limit(10).execute()
            team_allocations = team_resp.data if team_resp and team_resp.data else []

            # Recent emergency assignments (with incidents info)
            em_resp = supabase.table("emergency_assignments").select(
                "*, requests(id, incident_id, incidents(*))"
            ).order("assigned_at", desc=True).limit(25).execute()
            emergency_assignments = em_resp.data if em_resp and em_resp.data else []

            # Enrich assignments with unit and team lead info (avoid unsupported PostgREST joins)
            team_lead_ids = {a.get('team_lead_id') for a in emergency_assignments if a.get('team_lead_id')}
            unit_ids = {a.get('unit_id') for a in emergency_assignments if a.get('unit_id')}

            users_map = {}
            units_map = {}
            if team_lead_ids:
                try:
                    users_resp = supabase.table("users").select("id, name, email").in_("id", list(team_lead_ids)).execute()
                    for u in (users_resp.data or []):
                        users_map[u.get('id')] = u
                except Exception:
                    users_map = {}
            if unit_ids:
                try:
                    units_resp = supabase.table("emergency_units").select("id, unit_name, unit_category").in_("id", list(unit_ids)).execute()
                    for u in (units_resp.data or []):
                        units_map[u.get('id')] = u
                except Exception:
                    units_map = {}

            for a in emergency_assignments:
                lead = users_map.get(a.get('team_lead_id'))
                unit = units_map.get(a.get('unit_id'))
                if lead:
                    a['team_lead_name'] = lead.get('name')
                    a['team_lead_email'] = lead.get('email')
                if unit:
                    a['unit_name'] = unit.get('unit_name')
                    a['unit_category'] = unit.get('unit_category')

            active_assignments = len([a for a in emergency_assignments if (a.get('status') or '').lower() in ['assigned', 'enroute', 'onsite']])

            # Emergency heads (handle projects where is_emergency_head may not exist)
            try:
                heads_resp = supabase.table("users").select(
                    "id, name, email, is_emergency_head"
                ).eq("role", "emergency").eq("is_emergency_head", True).execute()
                emergency_heads = heads_resp.data if heads_resp and heads_resp.data else []
            except Exception:
                # Fallback: if the column doesn't exist yet, list all emergency users
                heads_resp = supabase.table("users").select(
                    "id, name, email"
                ).eq("role", "emergency").execute()
                emergency_heads = heads_resp.data if heads_resp and heads_resp.data else []

            # Emergency units
            units_resp = supabase.table("emergency_units").select(
                "id, unit_name, unit_category, status, head_id, users(name)"
            ).order("unit_name").execute()
            all_units = units_resp.data if units_resp and units_resp.data else []
            emergency_units = [u for u in all_units if (u.get('status') == 'Free')]

            # ✅ Government emergency updates (from the view)
            updates_resp = supabase.table("government_emergency_updates").select(
                "update_id, assignment_id, team_name, assignment_status, rescued_count, "
                "critical_count, severity, message, update_time, location, city, state"
            ).limit(20).execute()
            emergency_updates = updates_resp.data if updates_resp and updates_resp.data else []

        except Exception as err:
            flash(f"Error loading data: {err}", "danger")
    
    return render_template(
        "government_dashboard.html",
        requests=requests,
        pending_requests_list=pending_requests_list,
        notified_requests_list=notified_requests_list,
        team_allocations=team_allocations,
        emergency_assignments=emergency_assignments,
        emergency_heads=emergency_heads,
        emergency_units=emergency_units,
        emergency_updates=emergency_updates,
        total_requests=total_requests,
        pending_requests=pending_requests,
        active_assignments=active_assignments,
        completed_tasks=completed_tasks
    )

@app.route("/report_incident", methods=["GET", "POST"])
@handle_errors("report_incident", "Report incident failed:")
def report_incident():
    if "user" not in session:
        flash("Please sign in first!", "warning")
        return redirect(url_for("signin"))
    
    if request.method == "POST":
        location = request.form["location"].strip()
        address = request.form.get("address", "").strip()
        city = request.form.get("city", "").strip()
        state = request.form.get("state", "").strip()
        cause = request.form.get("cause", "").strip()
        pincode = request.form.get("pincode", "").strip()
        description = request.form["description"].strip()
        
        if not sb_available():
            flash("Database is not configured.", "danger")
            return redirect(url_for("report_incident"))

        if not pincode:
            flash("Pincode is required.", "danger")
            return redirect(url_for("report_incident"))

        try:
            inc_repo = IncidentRepository(supabase)
            inc_service = IncidentService(inc_repo, session=session)
            new_id = inc_service.report_incident(session["user_id"], {
                "location": location,
                "address": address,
                "city": city,
                "state": state,
                "cause": cause,
                "pincode": pincode,
                "description": description
            })
            if not new_id:
                flash("Could not report incident.", "danger")
            else:
                flash("Incident reported successfully!", "success")
        except Exception as err:
            flash(f"Error reporting incident: {err}", "danger")
        
        return redirect(url_for("report_incident"))
    
    return render_template("report_incident.html")

@app.route("/medical", methods=["GET", "POST"])
def medical():
    if "user" not in session:
        flash("Please sign in first!", "warning")
        return redirect(url_for("signin"))

    if request.method == "POST":
        request_type = request.form.get("request_type")
        description = request.form.get("description")
        urgency = request.form.get("urgency")

        if not sb_available():
            flash("Database is not configured.", "danger")
            return redirect(url_for("medical"))

        try:
            payload = {
                "user_id": session["user_id"],
                "request_type": request_type,
                "description": description,
                "urgency": urgency,
            }
            ins = supabase.table("medical_requests").insert(payload).execute()
            if not ins or not ins.data:
                flash("Could not submit request.", "danger")
            else:
                flash("Medical request submitted!", "success")
        except Exception as err:
            flash(f"Error submitting request: {err}", "danger")
        return redirect(url_for("medical"))

    return render_template("medical.html")

@app.route("/donate", methods=["GET", "POST"])
def donate():
    if "user" not in session:
        flash("Please sign in first!", "warning")
        return redirect(url_for("signin"))
    
    if request.method == "POST":
        amount = request.form.get("amount")
        method = request.form.get("payment_method")
        donor_name = request.form.get("donor_name", session.get("user_name", "Anonymous"))
        donor_email = request.form.get("donor_email", session.get("user_email", ""))
        
        if not amount:
            flash("Please enter donation amount", "danger")
            return redirect(url_for("donate"))
        
        if not sb_available():
            flash("Database is not configured.", "danger")
            return redirect(url_for("donate"))

        try:
            amount = float(amount)
            
            if method == "upi":
                # Generate direct UPI QR with fixed receiving UPI ID
                try:
                    receiver_upi = getattr(upi_payment_service, 'upi_id', None) or "devsakhya2004@okicici"
                    upi_link = f"upi://pay?pa={receiver_upi}&pn={donor_name}&am={amount}&cu=INR"
                    qr = qrcode.QRCode(version=1, error_correction=qrcode.constants.ERROR_CORRECT_L, box_size=10, border=4)
                    qr.add_data(upi_link)
                    qr.make(fit=True)
                    img = qr.make_image(fill_color="black", back_color="white")
                    buffer = io.BytesIO()
                    img.save(buffer, format='PNG')
                    qr_base64 = base64.b64encode(buffer.getvalue()).decode()
                    # Hold donation info in session until user confirms payment
                    session["donation_info"] = {
                        "user_id": session["user_id"],
                        "donor_name": donor_name,
                        "donor_email": donor_email,
                        "donor_upi": request.form.get("upi_id", ""),
                        "amount": amount
                    }
                    return render_template("donate_qr.html",
                                           qr_base64=qr_base64,
                                           amount=amount,
                                           donor_name=donor_name,
                                           donor_email=donor_email,
                                           donor_upi=session["donation_info"]["donor_upi"])
                except Exception as gen_err:
                    flash(f"Failed to generate UPI QR: {gen_err}", "danger")
            else:
                # Legacy donation method
                payload = {
                    "user_id": session["user_id"],
                    "amount": amount,
                    "method": method,
                    "donor_name": donor_name,
                    "donor_email": donor_email
                }
                # Only add status if the column exists
                try:
                    # Test if status column exists by trying to select it
                    test_resp = supabase.table("donations").select("status").limit(1).execute()
                    if test_resp.data:
                        payload["status"] = "completed"
                except:
                    # Status column doesn't exist yet, skip it
                    pass
                ins = supabase.table("donations").insert(payload).execute()
                if not ins or not ins.data:
                    flash("Error processing donation.", "danger")
                else:
                    flash("Thank you for your donation!", "success")
                    
        except ValueError:
            flash("Please enter a valid amount", "danger")
        except Exception as err:
            flash(f"Error processing donation: {err}", "danger")
        
        return redirect(url_for("donate"))
    
    # Get donation statistics (match admin dashboard logic and include static UPI flow)
    stats = {"total_amount": 0, "total_count": 0, "recent_donations": []}
    if sb_available():
        try:
            ok_status = ['verified', 'completed', 'success', 'paid']
            resp = supabase.table("donations").select("*").order("created_at", desc=True).limit(10).execute()
            rows = resp.data if resp and resp.data else []
            stats["recent_donations"] = [r for r in rows if (r.get('status') or '').lower() in ok_status]

            # Use separate queries for accurate totals
            all_resp = supabase.table("donations").select("amount, status").execute()
            all_rows = all_resp.data if all_resp and all_resp.data else []
            filtered = [r for r in all_rows if (r.get('status') or '').lower() in ok_status]
            stats["total_count"] = len(filtered)
            stats["total_amount"] = sum(float(r.get('amount', 0) or 0) for r in filtered)
        except Exception as _e:
            pass
    return render_template("donate.html", stats=stats)

@app.route("/donate/success")
def donate_success():
    donor_name = None
    try:
        # Optionally pass donor name from session (best-effort)
        if isinstance(session.get("donation_info"), dict):
            donor_name = session["donation_info"].get("donor_name")
    except Exception:
        pass
    return render_template("donate_success.html", donor_name=donor_name)

@app.route("/donate/qr", methods=["POST"])
def create_donation_qr():
    """Create UPI QR code for donation"""
    if "user" not in session:
        return jsonify({"error": "Please sign in first"}), 401
    
    data = request.get_json()
    amount = data.get("amount")
    donor_name = data.get("donor_name", session.get("user_name", "Anonymous"))
    donor_email = data.get("donor_email", session.get("user_email", ""))
    
    if not amount:
        return jsonify({"error": "Amount is required"}), 400
    
    try:
        qr_data = upi_payment_service.create_upi_payment_qr(
            amount=float(amount),
            user_id=session["user_id"],
            donor_name=donor_name,
            donor_email=donor_email
        )
        
        if qr_data:
            return jsonify(qr_data)
        else:
            return jsonify({"error": "Failed to create UPI QR code"}), 500
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/donate/verify", methods=["POST"])
def verify_donation():
    """Verify UPI payment"""
    if "user" not in session:
        return jsonify({"error": "Please sign in first"}), 401
    
    data = request.get_json()
    transaction_id = data.get("transaction_id")
    verification_code = data.get("verification_code")
    sender_upi_id = data.get("sender_upi_id")
    
    if not transaction_id:
        return jsonify({"error": "Missing transaction ID"}), 400
    
    try:
        success = upi_payment_service.verify_upi_payment(
            transaction_id=transaction_id,
            verification_code=verification_code,
            sender_upi_id=sender_upi_id
        )
        
        if success:
            # Ensure donation row is updated to a success-like status
            try:
                if sb_available():
                    supabase.table("donations").update({
                        "status": "verified",
                        "updated_at": "now()"
                    }).eq("id", transaction_id).execute()
            except Exception as e:
                print(f"Warning: could not update donation after verify: {e}")
            return jsonify({"success": True, "message": "Payment verified successfully"})
        else:
            return jsonify({"error": "Payment verification failed"}), 400
            
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/donate/mark_paid", methods=["POST"])
def mark_donation_paid():
    """Manually mark latest pending UPI donation as paid (for static UPI flow)"""
    if "user" not in session:
        flash("Please sign in first!", "warning")
        return redirect(url_for("signin"))
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("donate"))

@app.route("/donate/confirm", methods=["POST"])
def donate_confirm():
    if "donation_info" not in session:
        flash("No donation found to confirm.", "danger")
        return redirect(url_for("donate"))
    info = session.pop("donation_info")
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("donate"))
    try:
        supabase.table("donations").insert({
            "user_id": info.get("user_id"),
            "amount": info.get("amount"),
            "method": "upi",
            "donor_name": info.get("donor_name"),
            "donor_email": info.get("donor_email"),
            "upi_id": info.get("donor_upi"),
            "status": "success",
            "created_at": "now()"
        }).execute()
        flash("✅ Payment recorded! Thank you for donating ❤️", "success")
        return redirect(url_for("donate_success"))
    except Exception as err:
        flash(f"Error saving donation: {err}", "danger")
        return redirect(url_for("donate"))
    try:
        user_id = session.get("user_id")
        # Get latest pending donation for this user
        resp = supabase.table("donations").select("id").eq("user_id", user_id).eq("status", "pending").order("created_at", desc=True).limit(1).execute()
        row = resp.data[0] if resp and resp.data else None
        if not row:
            flash("No pending donation found to mark as paid.", "warning")
            return redirect(url_for("donate"))
        supabase.table("donations").update({"status": "success", "updated_at": "now()"}).eq("id", row["id"]).execute()
        flash("✅ Payment marked as successful! Thank you.", "success")
        return redirect(url_for("donate_success"))
    except Exception as err:
        flash(f"Error marking payment: {err}", "danger")
        return redirect(url_for("donate"))

@app.route("/donate/status/<int:transaction_id>", methods=["GET"])
def donation_status(transaction_id: int):
    """Return donation status for client polling."""
    if "user" not in session:
        return jsonify({"error": "Please sign in first"}), 401
    if not sb_available():
        return jsonify({"error": "Database not configured"}), 500
    try:
        result = supabase.table("donations").select("id, status, amount, amount_paid").eq("id", transaction_id).limit(1).execute()
        row = (result.data or [None])[0]
        if not row:
            return jsonify({"error": "Not found"}), 404
        status = (row.get("status") or "").lower()
        is_success = status in ["verified", "success", "completed"]
        return jsonify({
            "success": True,
            "status": status,
            "is_success": is_success,
            "amount": row.get("amount"),
            "amount_paid": row.get("amount_paid")
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/forward_incident", methods=["POST"])
@require_role("admin")
@handle_errors("admin_dashboard", "Forward incident failed:")
def forward_incident():
    incident_id = request.form.get("incident_id")
    if not incident_id:
        flash("Invalid incident ID", "danger")
        return redirect(url_for("admin_dashboard"))
    
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("admin_dashboard"))
    
    try:
        inc_repo = IncidentRepository(supabase)
        req_repo = RequestRepository(supabase)
        ann_repo = AnnouncementRepository(supabase)
        ann_service = AnnouncementService(ann_repo, UserRepository(supabase), session)
        inc_service = IncidentService(inc_repo, req_repo, ann_service, sms_service, Config, session)
        result = inc_service.forward_incident(session["user_id"], int(incident_id))
        if result.get("already"):
            flash("This incident has already been forwarded to government", "warning")
        elif result.get("forwarded"):
            flash("Incident forwarded to government successfully!", "success")
        else:
            flash("Unknown result while forwarding incident", "warning")
    except Exception as err:
        flash(f"Error forwarding incident: {err}", "danger")
    
    return redirect(url_for("admin_dashboard"))

@app.route("/create_announcement", methods=["POST"])
@require_role("admin")
@handle_errors("admin_dashboard", "Create announcement failed:")
def create_announcement():
    title = request.form.get("title")
    description = request.form.get("description")
    severity = request.form.get("severity", "medium")
    weather_data_id = request.form.get("weather_data_id")
    is_weather_alert = request.form.get("is_weather_alert") == "on"
    
    if not title or not description:
        flash("Title and description are required", "danger")
        return redirect(url_for("admin_dashboard"))
    
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("admin_dashboard"))
    
    try:
        payload = {
            "admin_id": session["user_id"],
            "title": title,
            "description": description,
            "severity": severity,
            "is_weather_alert": is_weather_alert,
        }
        
        # Add weather data reference if provided
        if weather_data_id:
            payload["weather_data_id"] = int(weather_data_id)
        
        ins = supabase.table("announcements").insert(payload).execute()
        if not ins or not ins.data:
            flash("Could not create announcement.", "danger")
        else:
            flash("Announcement created successfully!", "success")
    except Exception as err:
        flash(f"Error creating announcement: {err}", "danger")
    
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/data_view")
@require_role("admin")
def admin_data_view():
    """Admin route to view all database data"""
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("admin_dashboard"))
    
    try:
        # Fetch all data from Supabase
        incidents = []
        donations = []
        users = []
        announcements = []
        medical_requests = []
        
        # Get incidents
        inc_resp = supabase.table("incidents").select("*").order("timestamp", desc=True).execute()
        incidents = inc_resp.data if inc_resp and inc_resp.data else []
        
        # Get donations
        don_resp = supabase.table("donations").select("*").order("timestamp", desc=True).execute()
        donations = don_resp.data if don_resp and don_resp.data else []
        
        # Get users (excluding sensitive info)
        usr_resp = supabase.table("users").select("id, name, email, role, created_at").order("created_at", desc=True).execute()
        users = usr_resp.data if usr_resp and usr_resp.data else []
        
        # Get announcements
        ann_resp = supabase.table("announcements").select("*").order("timestamp", desc=True).execute()
        announcements = ann_resp.data if ann_resp and ann_resp.data else []
        
        # Get medical requests
        med_resp = supabase.table("medical_requests").select("*").order("created_at", desc=True).execute()
        medical_requests = med_resp.data if med_resp and med_resp.data else []
        
        # Get weather data
        weather_resp = supabase.table("weather_data").select("*").order("fetched_at", desc=True).limit(50).execute()
        weather_data = weather_resp.data if weather_resp and weather_resp.data else []
        
        return render_template("admin_data_view.html", 
                             incidents=incidents, 
                             donations=donations, 
                             users=users, 
                             announcements=announcements,
                             medical_requests=medical_requests,
                             weather_data=weather_data)
        
    except Exception as err:
        flash(f"Error fetching data: {err}", "danger")
        return redirect(url_for("admin_dashboard"))

@app.route("/allocate_team", methods=["POST"])
@require_role("government")
def allocate_team():
    request_id = request.form.get("request_id")
    team_name = request.form.get("team_name")
    
    if not request_id or not team_name:
        flash("Request ID and team name are required", "danger")
        return redirect(url_for("government_dashboard"))
    
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("government_dashboard"))
    
    try:
        payload = {
            "gov_id": session["user_id"],
            "request_id": int(request_id),
            "team_name": team_name,
        }
        ins = supabase.table("team_allocations").insert(payload).execute()
        if not ins or not ins.data:
            flash("Could not allocate team.", "danger")
        else:
            flash("Team allocated successfully!", "success")
    except Exception as err:
        flash(f"Error allocating team: {err}", "danger")
    
    return redirect(url_for("government_dashboard"))

@app.route("/notify_emergency_head", methods=["POST"])
@require_role("government")
@handle_errors("government_dashboard", "Notify emergency head failed:")
def notify_emergency_head():
    request_id = request.form.get("request_id")
    if not request_id:
        flash("Request is required", "danger")
        return redirect(url_for("government_dashboard"))
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("government_dashboard"))
    
    try:
        # Check if this request has already been notified
        existing_notification = supabase.table("emergency_notifications").select("id").eq("request_id", request_id).execute()
        if existing_notification and existing_notification.data:
            flash("This incident has already been notified to emergency teams. Status: Notified - Waiting for emergency team response.", "warning")
            return redirect(url_for("government_dashboard"))
        
        # Check if request status is already 'notified' or 'assigned'
        request_status = supabase.table("requests").select("status").eq("id", request_id).execute()
        if request_status and request_status.data:
            current_status = request_status.data[0].get('status')
            if current_status in ['notified', 'assigned', 'completed']:
                flash(f"This incident has already been processed. Current status: {current_status.title()}", "warning")
                return redirect(url_for("government_dashboard"))
        # Determine recipients without requiring email
        # 1) Heads
        heads = []
        try:
            resp = supabase.table("users").select("id, role, is_emergency_head").execute()
            rows = resp.data or []
            # prefer explicit heads
            for r in rows:
                if r.get("is_emergency_head"):
                    heads.append({"id": r.get("id")})
            # then add any role containing 'emergency'
            if not heads:
                for r in rows:
                    role_val = (r.get("role") or "").lower()
                    if "emergency" in role_val:
                        heads.append({"id": r.get("id")})
        except Exception:
            heads = []
        if not heads:
            # 2) fallback: notify owners of units
            try:
                unit_resp = supabase.table("emergency_units").select("head_id").execute()
                hid_set = {}
                for r in (unit_resp.data or []):
                    hid = r.get("head_id")
                    if hid:
                        hid_set[hid] = True
                heads = [{"id": k} for k in hid_set.keys()]
            except Exception:
                heads = []
        if not heads:
            flash("No emergency team users found to notify.", "danger")
            return redirect(url_for("government_dashboard"))
        # Insert one notification per head
        payloads = [
            {"request_id": int(request_id), "gov_id": session.get("user_id"), "head_id": h["id"], "status": "Pending"}
            for h in heads
        ]
        supabase.table("emergency_notifications").insert(payloads).execute()
        # Update request status -> notified
        try:
            supabase.table("requests").update({
                "status": "notified",
                "notified_at": datetime.now().isoformat()
            }).eq("id", request_id).execute()
        except Exception:
            pass
        flash("Notification sent to emergency teams. Status set to Notified.", "success")
    except Exception as err:
        flash(f"Error sending notification: {err}", "danger")
    return redirect(url_for("government_dashboard"))

@app.route("/emergency_dashboard")
@require_role("emergency")
def emergency_dashboard():
    assignments = []
    completed_assignments = []
    notifications = []
    my_units = []
    updates_map = {}
    total_assignments = 0
    active_assignments = 0
    rescued_count = 0
    completed_tasks = 0
    
    if sb_available():
        try:
            # All assignments for this emergency team user
            asg_resp = supabase.table("emergency_assignments").select("*, requests(incidents(location, description, pincode))").eq("team_lead_id", session.get("user_id")).order("assigned_at", desc=True).execute()
            all_assignments = asg_resp.data if asg_resp and asg_resp.data else []
            
            # Separate current and completed assignments
            assignments = [a for a in all_assignments if a.get('status') != 'Completed']
            completed_assignments = [a for a in all_assignments if a.get('status') == 'Completed']
            
            # Group current assignments by request_id to show multiple teams in same row
            grouped_assignments = {}
            for assignment in assignments:
                request_id = assignment.get('request_id')
                if request_id not in grouped_assignments:
                    grouped_assignments[request_id] = []
                grouped_assignments[request_id].append(assignment)
            
            # Convert grouped assignments back to list for template
            assignments = []
            for request_id, team_assignments in grouped_assignments.items():
                # Use the first assignment as the main row, but include all teams
                main_assignment = team_assignments[0]
                main_assignment['additional_teams'] = team_assignments[1:] if len(team_assignments) > 1 else []
                assignments.append(main_assignment)
            
            # Calculate statistics
            total_assignments = len(all_assignments)
            active_assignments = len(assignments)
            completed_tasks = len(completed_assignments)
            
            # Calculate total rescued count from updates
            for assignment in all_assignments:
                up_resp = supabase.table("emergency_updates").select("rescued_count").eq("assignment_id", assignment.get("id")).execute()
                if up_resp and up_resp.data:
                    for update in up_resp.data:
                        if update.get('rescued_count'):
                            rescued_count += int(update.get('rescued_count', 0))
            
            # Notifications to me if I am head
            notif_resp = supabase.table("emergency_notifications").select("*, requests(incidents(location, description))").eq("head_id", session.get("user_id")).order("created_at", desc=True).execute()
            notifications = notif_resp.data if notif_resp and notif_resp.data else []
            
            # Units under me if I am head
            units_resp = supabase.table("emergency_units").select("*").eq("head_id", session.get("user_id")).order("unit_name").execute()
            my_units = units_resp.data if units_resp and units_resp.data else []
            
            # Recent updates per assignment
            for a in assignments:
                up_resp = supabase.table("emergency_updates").select("*").eq("assignment_id", a.get("id")).order("created_at", desc=True).limit(3).execute()
                updates_map[a.get("id")] = up_resp.data if up_resp and up_resp.data else []
                
        except Exception as err:
            flash(f"Error loading assignments: {err}", "danger")
    
    return render_template("emergency_dashboard.html", 
                         assignments=assignments, 
                         completed_assignments=completed_assignments,
                         updates_map=updates_map, 
                         notifications=notifications, 
                         my_units=my_units,
                         total_assignments=total_assignments,
                         active_assignments=active_assignments,
                         rescued_count=rescued_count,
                         completed_tasks=completed_tasks)

@app.route("/create_unit", methods=["POST"])
@require_role("emergency")
def create_unit():
    unit_name = request.form.get("unit_name", "").strip()
    if not unit_name:
        flash("Team name is required.", "danger")
        return redirect(url_for("emergency_dashboard"))
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("emergency_dashboard"))
    try:
        categories = ["Rescue", "Escort", "Medical", "ResourceCollector"]
        payloads = [{
            "head_id": session.get("user_id"),
            "unit_name": unit_name,
            "unit_category": cat,
            "status": "Free",
        } for cat in categories]
        supabase.table("emergency_units").insert(payloads).execute()
        flash("Team created with Rescue, Escort, Medical, and ResourceCollector subteams.", "success")
    except Exception as err:
        flash(f"Error creating unit: {err}", "danger")
    return redirect(url_for("emergency_dashboard"))

@app.route("/head_assign_unit", methods=["POST"])
@require_role("emergency")
@handle_errors("emergency_dashboard", "Head assign unit failed:")
def head_assign_unit():
    # Only heads should use this: assign a free unit to a request → creates assignment with the unit name in notes
    request_id = request.form.get("request_id")
    unit_id = request.form.get("unit_id")
    if not all([request_id, unit_id]):
        flash("Request and unit are required", "danger")
        return redirect(url_for("emergency_dashboard"))
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("emergency_dashboard"))
    try:
        # Verify unit belongs to me and is Free
        u_resp = supabase.table("emergency_units").select("*, users(id)").eq("id", int(unit_id)).limit(1).execute()
        if not u_resp or not u_resp.data:
            flash("Unit not found", "danger")
            return redirect(url_for("emergency_dashboard"))
        unit = u_resp.data[0]
        # Mark unit Busy
        supabase.table("emergency_units").update({"status": "Busy", "last_update": None}).eq("id", int(unit_id)).execute()
        # Fetch incident location
        req_resp = supabase.table("requests").select("incident_id").eq("id", int(request_id)).limit(1).execute()
        incident_id = req_resp.data[0]["incident_id"] if req_resp and req_resp.data else None
        loc_text = None
        if incident_id:
            inc_resp = supabase.table("incidents").select("location").eq("id", incident_id).limit(1).execute()
            loc_text = inc_resp.data[0]["location"] if inc_resp and inc_resp.data else None
        # Create assignment under my user as lead
        payload = {
            "request_id": int(request_id),
            "team_name": unit["unit_name"],
            "team_type": unit["unit_category"],
            "team_lead_id": session.get("user_id"),
            "location_text": loc_text,
            "notes": f"Assigned unit #{unit['id']}",
            "status": "Assigned",
        }
        supabase.table("emergency_assignments").insert(payload).execute()
        # Move request out of pending/notified → assigned
        try:
            supabase.table("requests").update({
                "status": "assigned",
                "assigned_at": datetime.now().isoformat()
            }).eq("id", int(request_id)).execute()
        except Exception:
            pass
        # Mark notification acknowledged if exists
        supabase.table("emergency_notifications").update({"status": "Acknowledged"}).eq("request_id", int(request_id)).eq("head_id", session.get("user_id")).execute()
        flash("Unit assigned and government notified.", "success")
    except Exception as err:
        flash(f"Error assigning unit: {err}", "danger")
    return redirect(url_for("emergency_dashboard"))

@app.route("/delete_notification", methods=["POST"])
@require_role("emergency")
@handle_errors("emergency_dashboard", "Delete notification failed:")
def delete_notification():
    """Delete a government notification from emergency dashboard"""
    notification_id = request.form.get("notification_id")
    
    if not notification_id:
        flash("Notification ID is required", "danger")
        return redirect(url_for("emergency_dashboard"))
    
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("emergency_dashboard"))
    
    try:
        # Verify the notification belongs to current user
        notification_resp = supabase.table("emergency_notifications").select("id, head_id").eq("id", notification_id).eq("head_id", session.get("user_id")).execute()
        
        if not notification_resp or not notification_resp.data:
            flash("Notification not found or access denied", "danger")
            return redirect(url_for("emergency_dashboard"))
        
        # Delete the notification
        delete_result = supabase.table("emergency_notifications").delete().eq("id", notification_id).execute()
        
        if delete_result.data:
            flash("Notification deleted successfully!", "success")
        else:
            flash("Failed to delete notification.", "danger")
            
    except Exception as err:
        flash(f"Error deleting notification: {err}", "danger")
    
    return redirect(url_for("emergency_dashboard"))

@app.route("/emergency_update", methods=["POST"])
@require_role("emergency")
@handle_errors("emergency_dashboard", "Emergency update failed:")
def emergency_update():
    assignment_id = request.form.get("assignment_id")
    status = request.form.get("status")
    reached = request.form.get("reached") == "on"
    rescued_count = request.form.get("rescued_count")
    need_more_support = request.form.get("need_more_support") == "on"
    severity = request.form.get("severity")
    critical_count = request.form.get("critical_count")
    need_medical = request.form.get("need_medical") == "on"
    message = request.form.get("message")
    if not assignment_id:
        flash("Invalid assignment", "danger")
        return redirect(url_for("emergency_dashboard"))
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("emergency_dashboard"))
    try:
        payload = {
            "assignment_id": int(assignment_id),
            "author_id": session.get("user_id"),
            "reached": reached,
            "rescued_count": int(rescued_count) if rescued_count else None,
            "need_more_support": need_more_support,
            "severity": severity or None,
            "critical_count": int(critical_count) if critical_count else None,
            "need_medical": need_medical,
            "message": message or None,
        }
        supabase.table("emergency_updates").insert(payload).execute()
        
        # Optionally, update assignment status
        if status:
            supabase.table("emergency_assignments").update({"status": status}).eq("id", int(assignment_id)).execute()
        
        # Auto-create secondary requests if medical or additional support is needed
        if need_medical or need_more_support:
            try:
                # Get assignment details to find the original incident
                assignment_resp = supabase.table("emergency_assignments").select("*, requests(incident_id, incidents(*))").eq("id", assignment_id).execute()
                if assignment_resp and assignment_resp.data:
                    assignment_data = assignment_resp.data[0]
                    original_incident = assignment_data.get('requests', {}).get('incidents', {})
                    
                    if original_incident:
                        # Create a new incident for the secondary request
                        secondary_incident_payload = {
                            "user_id": session.get("user_id"),
                            "location": original_incident.get('location', 'Emergency Location'),
                            "address": original_incident.get('address'),
                            "city": original_incident.get('city'),
                            "state": original_incident.get('state'),
                            "pincode": original_incident.get('pincode'),
                            "description": f"Secondary request from Emergency Team Assignment #{assignment_id}. " + 
                                         ("Medical assistance needed. " if need_medical else "") +
                                         ("Additional support required. " if need_more_support else "") +
                                         f"Original message: {message or 'No additional details'}",
                            "severity": "high" if need_medical else "medium",
                            "status": "pending"
                        }
                        
                        # Insert secondary incident
                        secondary_incident_resp = supabase.table("incidents").insert(secondary_incident_payload).execute()
                        
                        if secondary_incident_resp and secondary_incident_resp.data:
                            secondary_incident_id = secondary_incident_resp.data[0]['id']
                            
                            # Get admin user ID for the request
                            admin_resp = supabase.table("users").select("id").eq("role", "admin").limit(1).execute()
                            admin_id = admin_resp.data[0]['id'] if admin_resp and admin_resp.data else session.get("user_id")
                            
                            # Create government request for the secondary incident
                            secondary_request_payload = {
                                "admin_id": admin_id,
                                "incident_id": secondary_incident_id,
                                "status": "pending"
                            }
                            
                            secondary_request_resp = supabase.table("requests").insert(secondary_request_payload).execute()
                            
                            if secondary_request_resp and secondary_request_resp.data:
                                flash("Update sent to government. Secondary request created for additional support!", "success")
                            else:
                                flash("Update sent to government. Failed to create secondary request.", "warning")
                        else:
                            flash("Update sent to government. Failed to create secondary incident.", "warning")
                    else:
                        flash("Update sent to government.", "success")
                else:
                    flash("Update sent to government.", "success")
            except Exception as secondary_err:
                print(f"Error creating secondary request: {secondary_err}")
                flash("Update sent to government. Failed to create secondary request.", "warning")
        else:
            flash("Update sent to government.", "success")
            
    except Exception as err:
        flash(f"Error sending update: {err}", "danger")
    return redirect(url_for("emergency_dashboard"))

@app.route("/update_assignment_status/<int:assignment_id>", methods=["POST"])
@require_role("emergency")
@handle_errors("emergency_dashboard", "Update assignment status failed:")
def update_assignment_status(assignment_id: int):
    """Update assignment status"""
    status = request.form.get("status")
    if not status:
        flash("Status is required", "danger")
        return redirect(url_for("emergency_dashboard"))
    
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("emergency_dashboard"))
    
    try:
        # Verify assignment belongs to current user
        assignment_resp = supabase.table("emergency_assignments").select("id, team_lead_id").eq("id", assignment_id).eq("team_lead_id", session.get("user_id")).execute()
        
        if not assignment_resp or not assignment_resp.data:
            flash("Assignment not found or access denied", "danger")
            return redirect(url_for("emergency_dashboard"))
        
        # Update assignment status
        update_result = supabase.table("emergency_assignments").update({
            "status": status
        }).eq("id", assignment_id).execute()
        
        if update_result.data:
            flash(f"Assignment status updated to {status}!", "success")
        else:
            flash("Failed to update assignment status.", "danger")
            
    except Exception as err:
        flash(f"Error updating assignment status: {err}", "danger")
    
    return redirect(url_for("emergency_dashboard"))

@app.route("/toggle_unit_status", methods=["POST"])
@require_role("emergency")
@handle_errors("emergency_dashboard", "Toggle unit status failed:")
def toggle_unit_status():
    unit_id = request.form.get("unit_id")
    if not unit_id:
        flash("Invalid unit", "danger")
        return redirect(url_for("emergency_dashboard"))
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("emergency_dashboard"))
    try:
        # Ensure unit belongs to me
        u_resp = supabase.table("emergency_units").select("id, head_id, status").eq("id", int(unit_id)).limit(1).execute()
        if not u_resp or not u_resp.data:
            flash("Unit not found", "danger")
            return redirect(url_for("emergency_dashboard"))
        unit = u_resp.data[0]
        # Toggle
        new_status = "Free" if unit.get("status") != "Free" else "Busy"
        supabase.table("emergency_units").update({"status": new_status}).eq("id", int(unit_id)).execute()
        flash("Unit status updated.", "success")
    except Exception as err:
        flash(f"Error updating unit: {err}", "danger")
    return redirect(url_for("emergency_dashboard"))

@app.route("/report_assignment_update", methods=["POST"])
@require_role("emergency")
@handle_errors("emergency_dashboard", "Report assignment update failed:")
def report_assignment_update():
    """Report an assignment update"""
    assignment_id = request.form.get("assignment_id")
    rescued_count = request.form.get("rescued_count")
    critical_count = request.form.get("critical_count")
    message = request.form.get("message")
    
    if not assignment_id:
        flash("Assignment ID is required", "danger")
        return redirect(url_for("emergency_dashboard"))
    
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("emergency_dashboard"))
    
    try:
        # Verify assignment belongs to current user
        assignment_resp = supabase.table("emergency_assignments").select("id, team_lead_id").eq("id", assignment_id).eq("team_lead_id", session.get("user_id")).execute()
        
        if not assignment_resp or not assignment_resp.data:
            flash("Assignment not found or access denied", "danger")
            return redirect(url_for("emergency_dashboard"))
        
        # Create update record
        payload = {
            "assignment_id": int(assignment_id),
            "author_id": session.get("user_id"),
            "rescued_count": int(rescued_count) if rescued_count else None,
            "critical_count": int(critical_count) if critical_count else None,
            "message": message or None,
        }
        
        supabase.table("emergency_updates").insert(payload).execute()
        flash("Assignment update reported successfully!", "success")
        
    except Exception as err:
        flash(f"Error reporting update: {err}", "danger")
    
    return redirect(url_for("emergency_dashboard"))

@app.route("/accept_request/<int:request_id>", methods=["POST"])
@require_role("government")
@handle_errors("government_dashboard", "Accept request failed:")
def accept_request(request_id: int):
    """Government accepts a request from admin"""
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("government_dashboard"))
    
    try:
        # Update request status to accepted
        update_result = supabase.table("requests").update({
            "status": "accepted",
            "accepted_at": datetime.now().isoformat()
        }).eq("id", request_id).execute()
        
        if update_result.data:
            flash("Request accepted successfully!", "success")
        else:
            flash("Failed to accept request.", "danger")
    except Exception as err:
        flash(f"Error accepting request: {err}", "danger")
    
    return redirect(url_for("government_dashboard"))

@app.route("/assign_emergency_team/<int:request_id>", methods=["POST"])
@require_role("government")
@handle_errors("government_dashboard", "Assign emergency team failed:")
def assign_emergency_team(request_id: int):
    """Government assigns emergency team to a request"""
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("government_dashboard"))
    
    try:
        # Update request status to 'assigned' (teams assigned, waiting for updates)
        update_result = supabase.table("requests").update({
            "status": "assigned",
            "assigned_at": datetime.now().isoformat()
        }).eq("id", request_id).execute()
        
        if update_result.data:
            flash("Emergency team(s) assigned. Status set to Assigned!", "success")
        else:
            flash("Failed to set request to Assigned.", "danger")
    except Exception as err:
        flash(f"Error assigning emergency team: {err}", "danger")
    
    return redirect(url_for("government_dashboard"))

@app.route("/complete_assignment", methods=["POST"])
@require_role("emergency")
@handle_errors("emergency_dashboard", "Complete assignment failed:")
def complete_assignment():
    """Complete an assignment"""
    assignment_id = request.form.get("assignment_id")
    completion_notes = request.form.get("completion_notes", "")
    
    if not assignment_id:
        flash("Assignment ID is required", "danger")
        return redirect(url_for("emergency_dashboard"))
    
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("emergency_dashboard"))
    
    try:
        # Verify assignment belongs to current user
        assignment_resp = supabase.table("emergency_assignments").select("id, team_lead_id").eq("id", assignment_id).eq("team_lead_id", session.get("user_id")).execute()
        
        if not assignment_resp or not assignment_resp.data:
            flash("Assignment not found or access denied", "danger")
            return redirect(url_for("emergency_dashboard"))
        
        # Get assignment details to update related records
        assignment_details = supabase.table("emergency_assignments").select("request_id").eq("id", assignment_id).execute()
        request_id = assignment_details.data[0]['request_id'] if assignment_details and assignment_details.data else None
        
        # Update assignment status to completed
        update_result = supabase.table("emergency_assignments").update({
            "status": "Completed",
            "completed_at": datetime.now().isoformat()
        }).eq("id", assignment_id).execute()
        
        if update_result.data:
            # Create completion update
            update_payload = {
                "assignment_id": int(assignment_id),
                "author_id": session.get("user_id"),
                "message": f"Assignment completed. {completion_notes}".strip(),
                "status": "completed"
            }
            supabase.table("emergency_updates").insert(update_payload).execute()
            
            # Update request status to completed
            if request_id:
                supabase.table("requests").update({
                    "status": "completed",
                    "completed_at": datetime.now().isoformat()
                }).eq("id", request_id).execute()
                
                # Update government notification status to completed
                supabase.table("emergency_notifications").update({
                    "status": "Completed"
                }).eq("request_id", request_id).execute()
            
            flash("Assignment completed successfully! Status updated in government dashboard.", "success")
        else:
            flash("Failed to complete assignment.", "danger")
            
    except Exception as err:
        flash(f"Error completing assignment: {err}", "danger")
    
    return redirect(url_for("emergency_dashboard"))

@app.route("/request_additional_support", methods=["POST"])
@require_role("emergency")
def request_additional_support():
    """Request additional support for an assignment"""
    assignment_id = request.form.get("assignment_id")
    support_type = request.form.get("support_type")
    urgency = request.form.get("urgency")
    support_message = request.form.get("support_message", "")
    
    if not assignment_id or not support_type or not urgency:
        flash("All fields are required", "danger")
        return redirect(url_for("emergency_dashboard"))
    
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("emergency_dashboard"))
    
    try:
        # Verify assignment belongs to current user
        assignment_resp = supabase.table("emergency_assignments").select("id, team_lead_id, requests(incident_id, incidents(*))").eq("id", assignment_id).eq("team_lead_id", session.get("user_id")).execute()
        
        if not assignment_resp or not assignment_resp.data:
            flash("Assignment not found or access denied", "danger")
            return redirect(url_for("emergency_dashboard"))
        
        assignment_data = assignment_resp.data[0]
        original_incident = assignment_data.get('requests', {}).get('incidents', {})
        
        if original_incident:
            # Create secondary incident for support request
            support_incident_payload = {
                "user_id": session.get("user_id"),
                "location": original_incident.get('location', 'Emergency Location'),
                "address": original_incident.get('address'),
                "city": original_incident.get('city'),
                "state": original_incident.get('state'),
                "pincode": original_incident.get('pincode'),
                "description": f"Support Request: {support_type.upper()} - {urgency.upper()} urgency. Assignment #{assignment_id}. {support_message}",
                "severity": "high" if urgency in ["high", "critical"] else "medium",
                "status": "pending"
            }
            
            support_incident_resp = supabase.table("incidents").insert(support_incident_payload).execute()
            
            if support_incident_resp and support_incident_resp.data:
                support_incident_id = support_incident_resp.data[0]['id']
                
                # Create request for government
                admin_resp = supabase.table("users").select("id").eq("role", "admin").limit(1).execute()
                admin_id = admin_resp.data[0]['id'] if admin_resp and admin_resp.data else session.get("user_id")
                
                support_request_payload = {
                    "admin_id": admin_id,
                    "incident_id": support_incident_id,
                    "status": "pending"
                }
                
                support_request_resp = supabase.table("requests").insert(support_request_payload).execute()
                
                if support_request_resp and support_request_resp.data:
                    # Create support update
                    support_update_payload = {
                        "assignment_id": int(assignment_id),
                        "author_id": session.get("user_id"),
                        "message": f"Support requested: {support_type} ({urgency} urgency). {support_message}",
                        "need_more_support": True,
                        "support_type": support_type,
                        "urgency": urgency
                    }
                    supabase.table("emergency_updates").insert(support_update_payload).execute()
                    
                    flash(f"Support request submitted successfully! Request ID: #{support_request_resp.data[0]['id']}", "success")
                else:
                    flash("Support request created but failed to notify government.", "warning")
            else:
                flash("Failed to create support request.", "danger")
        else:
            flash("Original incident not found.", "danger")
            
    except Exception as err:
        flash(f"Error requesting support: {err}", "danger")
    
    return redirect(url_for("emergency_dashboard"))

@app.route("/assign_more_teams", methods=["POST"])
@require_role("government")
@handle_errors("government_dashboard", "Assign more teams failed:")
def assign_more_teams():
    """Assign additional teams to an existing assignment"""
    assignment_id = request.form.get("assignment_id")
    unit_ids = request.form.getlist("unit_ids")
    notes = request.form.get("notes", "")
    
    if not assignment_id or not unit_ids:
        flash("Assignment ID and at least one unit are required", "danger")
        return redirect(url_for("government_dashboard"))
    
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("government_dashboard"))
    
    try:
        # Get the original assignment details
        assignment_resp = supabase.table("emergency_assignments").select("*, requests(incident_id, incidents(*))").eq("id", assignment_id).execute()
        
        if not assignment_resp or not assignment_resp.data:
            flash("Original assignment not found", "danger")
            return redirect(url_for("government_dashboard"))
        
        original_assignment = assignment_resp.data[0]
        original_incident = original_assignment.get('requests', {}).get('incidents', {})
        
        if not original_incident:
            flash("Original incident not found", "danger")
            return redirect(url_for("government_dashboard"))
        
        # Get available emergency heads
        heads_resp = supabase.table("users").select("id, name, email").eq("role", "emergency").limit(10).execute()
        emergency_heads = heads_resp.data if heads_resp and heads_resp.data else []
        
        if not emergency_heads:
            flash("No emergency heads available", "danger")
            return redirect(url_for("government_dashboard"))
        
        # Create additional assignments for each selected unit
        created_assignments = []
        for unit_id in unit_ids:
            # Get unit details
            unit_resp = supabase.table("emergency_units").select("*, users(name, email)").eq("id", unit_id).execute()
            
            if not unit_resp or not unit_resp.data:
                continue
            
            unit_data = unit_resp.data[0]
            team_lead = unit_data.get('users', {})
            
            # Assign to an available emergency head (round-robin)
            head_index = len(created_assignments) % len(emergency_heads)
            assigned_head = emergency_heads[head_index]
            
            # Create new assignment
            new_assignment_payload = {
                "request_id": original_assignment.get('request_id'),
                "team_lead_id": assigned_head['id'],
                "unit_id": int(unit_id),
                "status": "Assigned",
                "assigned_at": datetime.now().isoformat(),
                "notes": f"Additional team assignment. {notes}".strip()
            }
            
            assignment_result = supabase.table("emergency_assignments").insert(new_assignment_payload).execute()
            
            if assignment_result and assignment_result.data:
                created_assignments.append(assignment_result.data[0])
                
                # Create notification for the emergency head
                notification_payload = {
                    "head_id": assigned_head['id'],
                    "request_id": original_assignment.get('request_id'),
                    "message": f"Additional team assignment for incident at {original_incident.get('location', 'Emergency Location')}. Unit: {unit_data.get('unit_name', 'Emergency Unit')}",
                    "status": "Pending"
                }
                supabase.table("emergency_notifications").insert(notification_payload).execute()
        
        if created_assignments:
            flash(f"Successfully assigned {len(created_assignments)} additional team(s)!", "success")
        else:
            flash("Failed to assign additional teams", "danger")
            
    except Exception as err:
        flash(f"Error assigning additional teams: {err}", "danger")
    
    return redirect(url_for("government_dashboard"))

@app.route("/gov/delete_incident/<int:incident_id>", methods=["POST"])
@require_role("government")
@handle_errors("government_dashboard", "Delete incident failed:")
def gov_delete_incident(incident_id: int):
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("government_dashboard"))
    try:
        supabase.table("incidents").delete().eq("id", int(incident_id)).execute()
        flash("Incident deleted.", "success")
    except Exception as err:
        flash(f"Error deleting incident: {err}", "danger")
    return redirect(url_for("government_dashboard"))

# Allow government and emergency to delete an erroneous/duplicate emergency update
@app.route("/delete_update/<int:update_id>", methods=["POST"])
@handle_errors("government_dashboard", "Delete update failed:")
def delete_update(update_id: int):
    user_role = session.get("user_role")
    user_id = session.get("user_id")
    if user_role not in ["government", "emergency"]:
        flash("Access denied", "danger")
        return redirect(url_for("dashboard"))
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("dashboard"))
    try:
        # Emergency can delete only their own updates; Government can delete any
        if user_role == "emergency":
            up = supabase.table("emergency_updates").select("id, author_id").eq("id", update_id).limit(1).execute()
            if not up or not up.data or up.data[0].get("author_id") != user_id:
                flash("Update not found or access denied", "danger")
                return redirect(url_for("emergency_dashboard"))
        # Perform delete
        supabase.table("emergency_updates").delete().eq("id", update_id).execute()
        flash("Update deleted.", "success")
    except Exception as err:
        flash(f"Error deleting update: {err}", "danger")
    # Redirect back based on role
    return redirect(url_for("government_dashboard" if user_role == "government" else "emergency_dashboard"))

@app.route("/notify_admin_resolved", methods=["POST"])
@require_role("government")
@handle_errors("government_dashboard", "Notify admin resolved failed:")
def notify_admin_resolved():
    """Government notifies admin that disaster is resolved"""
    request_id = request.form.get("request_id")
    resolution_notes = request.form.get("resolution_notes", "")
    
    if not request_id:
        flash("Request ID is required", "danger")
        return redirect(url_for("government_dashboard"))
    
    if not sb_available():
        flash("Database is not configured.", "danger")
        return redirect(url_for("government_dashboard"))
    
    try:
        # Get the original incident from the request
        req_resp = supabase.table("requests").select("*, incidents(*)").eq("id", request_id).execute()
        if not req_resp or not req_resp.data:
            flash("Request not found", "danger")
            return redirect(url_for("government_dashboard"))
        
        request_data = req_resp.data[0]
        incident_data = request_data.get('incidents', {})
        
        if not incident_data:
            flash("Incident data not found", "danger")
            return redirect(url_for("government_dashboard"))
        
        # Update incident status to resolved
        supabase.table("incidents").update({
            "status": "resolved",
            "resolved_at": datetime.now().isoformat()
        }).eq("id", incident_data['id']).execute()
        
        # Update request status to completed
        supabase.table("requests").update({
            "status": "completed",
            "completed_at": datetime.now().isoformat()
        }).eq("id", request_id).execute()
        
        # Create admin notification announcement
        admin_resp = supabase.table("users").select("id").eq("role", "admin").limit(1).execute()
        admin_id = admin_resp.data[0]['id'] if admin_resp and admin_resp.data else session.get("user_id")
        
        resolution_announcement = {
            "admin_id": admin_id,
            "title": f"✅ DISASTER RESOLVED - {incident_data.get('location', 'Emergency Location')}",
            "description": f"""
🎉 DISASTER RESOLUTION CONFIRMED 🎉

Location: {incident_data.get('location', 'Emergency Location')}
Pincode: {incident_data.get('pincode', 'Not specified')}
Original Incident ID: #{incident_data.get('id')}
Request ID: #{request_id}

✅ STATUS: DISASTER SUCCESSFULLY RESOLVED
📅 Resolved: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
👥 Resolved by: Government Emergency Response Team

📝 Resolution Notes:
{resolution_notes if resolution_notes else 'Emergency response completed successfully. All affected areas have been secured and assistance provided.'}

🔔 ADMIN ACTION REQUIRED:
Please review and consider removing the disaster announcement for this location as the emergency has been resolved.

Stay safe and thank you for your coordination.
- Government Emergency Management Team
            """.strip(),
            "severity": "low",
            "is_weather_alert": False,
            "timestamp": "now()"
        }
        
        ann_result = supabase.table("announcements").insert(resolution_announcement).execute()
        
        if ann_result and ann_result.data:
            flash("✅ Disaster marked as resolved! Admin has been notified to review announcements.", "success")
        else:
            flash("Disaster marked as resolved but failed to notify admin.", "warning")
            
    except Exception as err:
        flash(f"Error marking disaster as resolved: {err}", "danger")
    
    return redirect(url_for("government_dashboard"))

@app.route("/nearby_shelters", methods=["GET", "POST"])
def nearby_shelters():
    shelters = []
    user_location = ""
    
    if request.method == "POST":
        user_location = request.form.get("location")

        if not user_location:
            flash("Please enter a location", "warning")
            return redirect(url_for("nearby_shelters"))

        try:
            # Get user coordinates using geopy with timeout
            geolocator = Nominatim(user_agent="disaster_management", timeout=10)
            location = geolocator.geocode(user_location, timeout=10)
            
            if not location:
                flash("Could not find the location. Please try a different address.", "warning")
                return redirect(url_for("nearby_shelters"))
            
            user_lat, user_lon = location.latitude, location.longitude
            
            # Search for shelters using Overpass API (OpenStreetMap)
            api = overpy.Overpass()
            
            # Query for public gathering places: schools, colleges, auditoriums, museums, parks
            query = f"""
            [out:json][timeout:25];
            (
              node["amenity"="shelter"](around:10000,{user_lat},{user_lon});
              node["building"="school"](around:10000,{user_lat},{user_lon});
              node["building"="college"](around:10000,{user_lat},{user_lon});
              node["amenity"="community_centre"](around:10000,{user_lat},{user_lon});
              node["amenity"="place_of_worship"](around:10000,{user_lat},{user_lon});
              node["building"="church"](around:10000,{user_lat},{user_lon});
              node["building"="temple"](around:10000,{user_lat},{user_lon});
              node["building"="mosque"](around:10000,{user_lat},{user_lon});
              node["amenity"="auditorium"](around:10000,{user_lat},{user_lon});
              node["tourism"="museum"](around:10000,{user_lat},{user_lon});
              node["leisure"="park"](around:10000,{user_lat},{user_lon});
              node["leisure"="sports_centre"](around:10000,{user_lat},{user_lon});
              node["amenity"="theatre"](around:10000,{user_lat},{user_lon});
              node["amenity"="conference_centre"](around:10000,{user_lat},{user_lon});
              way["amenity"="shelter"](around:10000,{user_lat},{user_lon});
              way["building"="school"](around:10000,{user_lat},{user_lon});
              way["building"="college"](around:10000,{user_lat},{user_lon});
              way["amenity"="community_centre"](around:10000,{user_lat},{user_lon});
              way["amenity"="place_of_worship"](around:10000,{user_lat},{user_lon});
              way["building"="church"](around:10000,{user_lat},{user_lon});
              way["building"="temple"](around:10000,{user_lat},{user_lon});
              way["building"="mosque"](around:10000,{user_lat},{user_lon});
              way["amenity"="auditorium"](around:10000,{user_lat},{user_lon});
              way["tourism"="museum"](around:10000,{user_lat},{user_lon});
              way["leisure"="park"](around:10000,{user_lat},{user_lon});
              way["leisure"="sports_centre"](around:10000,{user_lat},{user_lon});
              way["amenity"="theatre"](around:10000,{user_lat},{user_lon});
              way["amenity"="conference_centre"](around:10000,{user_lat},{user_lon});
            );
            out body;
            >;
            out skel qt;
            """
            
            result = api.query(query)
            
            # Process results
            for node in result.nodes:
                # Only include places with actual names, skip generic ones
                shelter_name = node.tags.get("name")
                if not shelter_name or shelter_name in ["", "Unnamed", "Unknown"]:
                    continue
                
                # Determine shelter type based on tags
                if node.tags.get("amenity") == "shelter":
                    shelter_type = "Emergency Shelter"
                elif node.tags.get("building") == "school":
                    shelter_type = "School"
                elif node.tags.get("building") == "college":
                    shelter_type = "College"
                elif node.tags.get("amenity") == "place_of_worship":
                    shelter_type = "Place of Worship"
                elif node.tags.get("building") in ["church", "temple", "mosque"]:
                    shelter_type = node.tags.get("building").title()
                elif node.tags.get("amenity") == "community_centre":
                    shelter_type = "Community Center"
                elif node.tags.get("amenity") == "auditorium":
                    shelter_type = "Auditorium"
                elif node.tags.get("tourism") == "museum":
                    shelter_type = "Museum"
                elif node.tags.get("leisure") == "park":
                    shelter_type = "Park"
                elif node.tags.get("leisure") == "sports_centre":
                    shelter_type = "Sports Center"
                elif node.tags.get("amenity") == "theatre":
                    shelter_type = "Theater"
                elif node.tags.get("amenity") == "conference_centre":
                    shelter_type = "Conference Center"
                else:
                    shelter_type = "Public Facility"
                
                # Calculate distance
                shelter_lat = float(node.lat)
                shelter_lon = float(node.lon)
                distance = geodesic((user_lat, user_lon), (shelter_lat, shelter_lon)).kilometers
                
                # Get contact information
                phone = node.tags.get("phone") or node.tags.get("contact:phone") or "Contact not available"
                
                # Estimate capacity based on type
                if shelter_type in ["School", "College"]:
                    capacity = "Large (500+ people)"
                elif shelter_type in ["Church", "Temple", "Mosque"]:
                    capacity = "Medium (100-500 people)"
                elif shelter_type == "Park":
                    capacity = "Very Large (1000+ people)"
                elif shelter_type == "Museum":
                    capacity = "Medium (200-500 people)"
                elif shelter_type in ["Auditorium", "Theater"]:
                    capacity = "Large (300-800 people)"
                elif shelter_type == "Conference Center":
                    capacity = "Large (200-1000 people)"
                elif shelter_type == "Sports Center":
                    capacity = "Very Large (500+ people)"
                else:
                    capacity = "Contact for details"
                
                shelters.append({
                    "name": shelter_name,
                    "type": shelter_type,
                    "address": f"Lat: {shelter_lat:.4f}, Lon: {shelter_lon:.4f}",
                    "distance": f"{distance:.1f} km",
                    "lat": shelter_lat,
                    "lon": shelter_lon,
                    "capacity": capacity,
                    "phone": phone
                })
            
            # Also get shelters from database as backup
            if sb_available():
                try:
                    resp = supabase.table("shelters").select("*").execute()
                    db_shelters = resp.data if resp and resp.data else []
                    
                    for shelter in db_shelters:
                        # Calculate distance to database shelter
                        shelter_lat = 0  # You'd need to add lat/lon to your database
                        shelter_lon = 0
                        distance = geodesic((user_lat, user_lon), (shelter_lat, shelter_lon)).kilometers if shelter_lat != 0 else "N/A"
                        
                        shelters.append({
                            "name": shelter["name"],
                            "type": "Database Shelter",
                            "address": shelter["location"],
                            "capacity": f"{shelter['available']}/{shelter['capacity']}",
                            "distance": f"{distance:.1f} km" if distance != "N/A" else "N/A",
                            "lat": shelter_lat,
                            "lon": shelter_lon
                        })
                except Exception as err:
                    pass  # Continue with OSM results
            
            # Sort by distance (nearest first)
            shelters.sort(key=lambda x: float(x["distance"].split()[0]) if x["distance"] != "N/A" else float('inf'))
            
            if not shelters:
                flash("No shelters found nearby. Try expanding your search area.", "info")
            
        except Exception as err:
            flash(f"Error fetching shelters: {err}", "danger")
            # Fallback to database shelters
            if sb_available():
                try:
                    resp = supabase.table("shelters").select("*").execute()
                    db_shelters = resp.data if resp and resp.data else []
                    
                    for shelter in db_shelters:
                        shelters.append({
                            "name": shelter["name"],
                            "type": "Database Shelter",
                            "address": shelter["location"],
                            "capacity": f"{shelter['available']}/{shelter['capacity']}",
                            "distance": "N/A",
                            "lat": 0,
                            "lon": 0
                        })
                except Exception:
                    pass

    return render_template("nearby_shelters.html", shelters=shelters, user_location=user_location)

@app.route("/announcements")
def announcements():
    if "user" not in session:
        flash("Please sign in first!", "warning")
        return redirect(url_for("signin"))
    
    announcements = []
    if sb_available():
        try:
            # Check and update weather alerts (remove resolved ones)
            check_and_update_weather_alerts()
            
            resp = supabase.table("announcements").select("*, weather_data!announcements_weather_data_id_fkey(*)").order("timestamp", desc=True).execute()
            announcements = resp.data if resp and resp.data else []
        except Exception as err:
            flash(f"Error fetching announcements: {err}", "danger")
    
    return render_template("announcements.html", announcements=announcements)

@app.route("/logout")
def logout():
    session.pop("user", None)
    session.pop("user_id", None)
    session.pop("user_email", None)
    session.pop("user_role", None)
    try:
        if sb_available():
            supabase.auth.sign_out()
    except Exception:
        pass
    flash("Logged out successfully!", "info")
    return redirect(url_for("home"))

@app.route("/donations/pending")
@require_role("admin")
def pending_donations():
    """View pending donations for admin verification"""
    try:
        pending_donations = upi_payment_service.get_pending_donations()
        return render_template("pending_donations.html", donations=pending_donations)
    except Exception as e:
        flash(f"Error fetching pending donations: {e}", "danger")
        return redirect(url_for("admin_dashboard"))

@app.route("/donations/verify/<transaction_id>", methods=["POST"])
@require_role("admin")
def admin_verify_donation(transaction_id):
    """Admin verify donation"""
    verification_code = request.form.get("verification_code", "")
    
    try:
        success = upi_payment_service.verify_upi_payment(transaction_id, verification_code)
        if success:
            flash("Donation verified successfully!", "success")
        else:
            flash("Failed to verify donation", "danger")
    except Exception as e:
        flash(f"Error verifying donation: {e}", "danger")
    
    return redirect(url_for("pending_donations"))

if __name__ == "__main__":
    app.run(debug=True)