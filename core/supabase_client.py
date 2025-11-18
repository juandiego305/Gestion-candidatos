# core/supabase_client.py
import os
from supabase import create_client, Client, ClientOptions
from dotenv import load_dotenv
from httpx import Client as HTTPXClient

# Cargar variables
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise Exception("❌ VARIABLES SUPABASE_URL O SUPABASE_SERVICE_KEY NO DEFINIDAS.")

def get_supabase():
    # Forzar HTTP/1.1 para evitar fallos de httpx
    http_client = HTTPXClient(http2=False)

    # Crear opciones correctas (NO un dict)
    options = ClientOptions(
        postgrest_client_timeout=30,
        storage_client_timeout=30,
        httpx_client=http_client 
    )

    return create_client(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_SERVICE_KEY,
        options=options
    )

# Crear cliente global
supabase: Client = get_supabase()

print("✅ Conectado exitosamente a Supabase")
