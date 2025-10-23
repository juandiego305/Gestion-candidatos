# core/supabase_client.py
import os
from supabase import create_client, Client
from dotenv import load_dotenv

# 🔹 Cargar las variables de entorno desde el archivo .env
load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_KEY = os.getenv("SUPABASE_SERVICE_KEY")

# 🔹 Validar que las variables existan
if not SUPABASE_URL or not SUPABASE_SERVICE_KEY:
    raise Exception("❌ Las variables SUPABASE_URL o SUPABASE_SERVICE_KEY no están definidas en el archivo .env")

# 🔹 Crear la conexión con Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)
print("✅ Conectado exitosamente a Supabase")
