from typing import Optional


class AnnouncementRepository:
    def __init__(self, supabase_client):
        self.supabase = supabase_client

    def create(self, payload: dict) -> Optional[int]:
        res = self.supabase.table("announcements").insert(payload).execute()
        if res and res.data:
            return res.data[0]['id']
        return None

    def update(self, announcement_id: int, payload: dict) -> bool:
        res = self.supabase.table("announcements").update(payload).eq("id", announcement_id).execute()
        return bool(res and res.data)

    def find_weather_alert_by_title(self, title: str) -> Optional[dict]:
        res = self.supabase.table("announcements").select("id,title,description,severity,weather_data_id,is_weather_alert,timestamp").eq("is_weather_alert", True).eq("title", title).limit(1).execute()
        if res and res.data:
            return res.data[0]
        return None

    def delete(self, announcement_id: int) -> bool:
        self.supabase.table("announcements").delete().eq("id", announcement_id).execute()
        return True

    def count(self) -> int:
        try:
            resp = self.supabase.table('announcements').select('id', count='exact').limit(1).execute()
            return getattr(resp, 'count', None) or 0
        except Exception:
            return 0


