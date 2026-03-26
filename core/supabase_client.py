import os

from supabase import Client, create_client


supabase_url = os.getenv("SUPABASE_URL")
supabase_service_key = os.getenv("SUPABASE_SERVICE_KEY")

if supabase_url and supabase_service_key:
    supabase: Client = create_client(supabase_url, supabase_service_key)
else:
    supabase = None
