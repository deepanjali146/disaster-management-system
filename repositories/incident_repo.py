from typing import Optional


class IncidentRepository:
    def __init__(self, supabase_client):
        self.supabase = supabase_client

    def insert_incident(self, payload: dict) -> Optional[int]:
        res = self.supabase.table('incidents').insert(payload).execute()
        if res and res.data:
            return res.data[0]['id']
        return None

    def get_incident(self, incident_id: int) -> Optional[dict]:
        res = self.supabase.table('incidents').select('*').eq('id', incident_id).limit(1).execute()
        return res.data[0] if res and res.data else None

    def update_incident_forwarded(self, incident_id: int, forwarded_at: str) -> bool:
        res = self.supabase.table('incidents').update({
            'status': 'forwarded',
            'forwarded_at': forwarded_at
        }).eq('id', incident_id).execute()
        return bool(res and res.data)


