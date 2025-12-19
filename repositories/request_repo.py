class RequestRepository:
    def __init__(self, supabase_client):
        self.supabase = supabase_client

    def insert_request(self, payload: dict):
        return self.supabase.table('requests').insert(payload).execute()


