import os
from dotenv import load_dotenv
from httpx import Client as HTTPXClient
from supabase import create_client, Client, ClientOptions

# Cargar variables de entorno
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise Exception("❌ VARIABLES SUPABASE_URL O SUPABASE_SERVICE_KEY NO DEFINIDAS.")


def get_supabase_client() -> Client:
    """Retorna una instancia de Supabase configurada."""
    
    http_client = HTTPXClient(http2=False)

    options = ClientOptions(
        storage_client_timeout=30,
        postgrest_client_timeout=30,
        httpx_client=http_client
    )

    return create_client(
        supabase_url=SUPABASE_URL,
        supabase_key=SUPABASE_SERVICE_KEY,
        options=options
    )


# Cliente global reutilizable
supabase: Client = get_supabase_client()

print("✅ Conectado exitosamente a Supabase")
