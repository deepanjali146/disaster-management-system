from typing import Optional


class UserRepository:
    def __init__(self, supabase_client):
        self.supabase = supabase_client

    def get_any_admin_id(self) -> Optional[str]:
        resp = self.supabase.table("users").select("id").eq("role", "admin").limit(1).execute()
        if resp and resp.data:
            return resp.data[0]['id']
        return None

    def upsert_user_profile(self, profile: dict):
        self.supabase.table("users").upsert(profile, on_conflict="id").execute()

    def get_email_by_phone(self, phone: str) -> Optional[str]:
        resp = self.supabase.table("users").select("email").eq("phone", phone).limit(1).execute()
        if resp and resp.data:
            return (resp.data[0].get("email") or "").lower()
        return None

    def get_profile_basic(self, user_id: str) -> Optional[dict]:
        resp = self.supabase.table("users").select("id,name,email,role").eq("id", user_id).limit(1).execute()
        return resp.data[0] if resp and resp.data else None


