import psycopg2
import os
from dotenv import load_dotenv

# Cargar las variables del .env
load_dotenv()

DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")

print("🔍 Probando conexión con Supabase...")
try:
    conn = psycopg2.connect(
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT
    )
    print("✅ Conectado exitosamente a Supabase")
    conn.close()
except Exception as e:
    print("❌ Error al conectar:", e)
