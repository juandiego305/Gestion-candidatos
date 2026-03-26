#!/usr/bin/env python
import os
from dotenv import load_dotenv

# Cargar .env explícitamente
load_dotenv(override=True)

# Verificar que se cargó la nueva API key ANTES de importar Django
new_api_key = os.getenv("SENDGRID_API_KEY")
print(f"📧 API Key cargada del .env: {new_api_key[:25]}...")

# Ahora sí importar Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gestion_de_candidatos.settings')
import django
django.setup()

from django.conf import settings
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

print(f"API Key en settings.SENDGRID_API_KEY: {settings.SENDGRID_API_KEY[:25]}...")
print(f"From Email: {settings.DEFAULT_FROM_EMAIL}")

# Comparar
if new_api_key == settings.SENDGRID_API_KEY:
    print("✅ API Key coincide!")
else:
    print("❌ API Key NO coincide - usando la de settings.py")

try:
    print("\n🚀 Enviando email de prueba...")
    sg = SendGridAPIClient(settings.SENDGRID_API_KEY)
    message = Mail(
        from_email=settings.DEFAULT_FROM_EMAIL,
        to_emails="delgadoyeffersondavid@gmail.com",
        subject="🧪 Test SendGrid - Nueva API Key",
        html_content="<strong>Test de SendGrid con nueva API key</strong><p>Si recibes este email, ¡la API key funciona!</p>"
    )
    
    response = sg.send(message)
    print(f"✅ Email de prueba enviado exitosamente!")
    print(f"Status Code: {response.status_code}")
except Exception as e:
    print(f"❌ Error: {str(e)}")
    print(f"Tipo de error: {type(e).__name__}")
