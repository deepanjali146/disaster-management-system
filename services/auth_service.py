class AuthService:
    def __init__(self, supabase_client, user_repo):
        self.supabase = supabase_client
        self.user_repo = user_repo

    def signup(self, name: str, email: str, phone: str, password: str, place: str, city: str, state: str, pincode: str, role: str):
        auth_res = self.supabase.auth.sign_up({
            "email": email,
            "password": password,
            "options": {"data": {"name": name, "phone": phone, "role": role}}
        })
        if not auth_res or not auth_res.user:
            return None
        user_id = auth_res.user.id
        profile = {
            "id": user_id,
            "name": name,
            "email": email,
            "phone": phone,
            "place": place,
            "city": city,
            "state": state,
            "pincode": pincode,
            "role": role,
        }
        self.user_repo.upsert_user_profile(profile)
        return user_id

    def signin(self, email_or_phone: str, password: str):
        email = email_or_phone
        if "@" not in email_or_phone:
            email_lookup = self.user_repo.get_email_by_phone(email_or_phone)
            if not email_lookup:
                return None
            email = email_lookup
        auth_res = self.supabase.auth.sign_in_with_password({
            "email": email.lower(),
            "password": password
        })
        if not auth_res or not auth_res.user:
            return None
        user_id = auth_res.user.id
        profile = self.user_repo.get_profile_basic(user_id)
        if not profile:
            # create minimal profile if missing
            self.user_repo.upsert_user_profile({
                "id": user_id,
                "name": email.split("@")[0],
                "email": email.lower(),
                "role": "user"
            })
            profile = self.user_repo.get_profile_basic(user_id)
        return {"user_id": user_id, "profile": profile}


