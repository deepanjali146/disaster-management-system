from typing import Optional


class AnnouncementService:
    def __init__(self, announcement_repo, user_repo=None, session=None):
        self.ann_repo = announcement_repo
        self.user_repo = user_repo
        self.session = session or {}

    def create_weather_alert(self, weather_data: dict, weather_id: Optional[int]):
        # Determine severity
        severity = "high"
        cond = weather_data.get('weather_condition')
        temp = weather_data.get('temperature')
        wind = weather_data.get('wind_speed')
        if cond in ['Thunderstorm', 'Tornado', 'Hurricane']:
            severity = 'critical'
        elif temp is not None and (temp > 40 or temp < -10):
            severity = 'critical'
        elif wind is not None and wind > 20:
            severity = 'high'

        location = weather_data.get('location')
        title = f"Extreme Weather Alert - {location}"
        desc = f"Extreme weather conditions detected in {location}. "
        if weather_data.get('weather_alert'):
            desc += f"Alert: {weather_data.get('weather_alert')}. "
        desc += f"Current conditions: {cond}, Temperature: {temp}°C"
        if wind:
            desc += f", Wind Speed: {wind} km/h"
        desc += ". Please take necessary precautions and stay safe."

        admin_id = None
        if self.session.get('user_role') == 'admin':
            admin_id = self.session.get('user_id')
        elif self.user_repo is not None:
            admin_id = self.user_repo.get_any_admin_id()

        payload = {
            'title': title,
            'description': desc,
            'severity': severity,
            'is_weather_alert': True,
            'weather_data_id': weather_id if weather_id else None
        }
        if admin_id:
            payload['admin_id'] = admin_id

        # Upsert behavior: if an alert for the same city/title exists, update instead of creating a duplicate
        existing = self.ann_repo.find_weather_alert_by_title(title)
        if existing:
            self.ann_repo.update(existing['id'], {
                'description': payload['description'],
                'severity': payload['severity'],
                'weather_data_id': payload.get('weather_data_id')
            })
            return existing['id']
        else:
            return self.ann_repo.create(payload)


