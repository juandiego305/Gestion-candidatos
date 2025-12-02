# Configuración de SendGrid para Envío de Correos en Producción

## 🚨 Problema Identificado

**Render.com (y muchas plataformas gratuitas) bloquean el puerto 587 (SMTP)** para prevenir spam. Por esto, los correos funcionan en local pero NO en producción.

## ✅ Solución: SendGrid

SendGrid usa API HTTP (no SMTP), por lo que funciona perfectamente en Render.
- **Gratis**: 100 correos/día (suficiente para empezar)
- **Confiable**: Entrega garantizada
- **Rápido**: API HTTP más rápida que SMTP

---

## 📋 Pasos para Configurar SendGrid

### 1. Crear Cuenta en SendGrid

1. Ve a [https://signup.sendgrid.com/](https://signup.sendgrid.com/)
2. Crea una cuenta gratuita
3. Verifica tu email

### 2. Crear API Key

1. Una vez dentro, ve a **Settings** → **API Keys**
2. Click en **"Create API Key"**
3. Nombre: `gestion-candidatos-production`
4. Permissions: **Full Access** (o solo **Mail Send** si prefieres)
5. Click **"Create & View"**
6. **⚠️ IMPORTANTE**: Copia la API Key inmediatamente (solo se muestra una vez)
   - Ejemplo: `SG.xxxxxxxxxxx-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`

### 3. Verificar Dominio de Remitente (Sender Identity)

SendGrid requiere que verifiques tu identidad antes de enviar correos:

**Opción A: Single Sender Verification** (más fácil, recomendado para empezar)

1. Ve a **Settings** → **Sender Authentication**
2. Click en **"Single Sender Verification"**
3. Click **"Create New Sender"**
4. Completa el formulario:
   - **From Name**: TalentoHub
   - **From Email Address**: talentohub2025@gmail.com
   - **Reply To**: talentohub2025@gmail.com
   - **Company Address**: (cualquier dirección)
5. Click **"Create"**
6. **Verifica tu email** (SendGrid enviará un correo a talentohub2025@gmail.com)
7. Abre el correo y click en el link de verificación

**Opción B: Domain Authentication** (más profesional, requiere acceso a DNS)

- Solo necesario si quieres usar un dominio personalizado
- Requiere agregar registros DNS (CNAME, TXT)
- Salta esto por ahora y usa Single Sender

### 4. Agregar API Key a Render

1. Ve a **Render Dashboard** → tu servicio → **Environment**
2. Agrega la variable:
   ```
   SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
   (Usa el valor que copiaste en el paso 2)

3. Asegúrate de tener también:
   ```
   EMAIL_HOST_USER=talentohub2025@gmail.com
   EMAIL_HOST_PASSWORD=ejsu oaiq zivq zdus
   ```

4. **Save Changes** (Render redeployará automáticamente)

---

## 🧪 Probar la Configuración

### Opción 1: Desde tu computadora local

```powershell
pip install sendgrid
```

Luego ejecuta en Python:

```python
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

API_KEY = "SG.tu-api-key-aqui"
FROM_EMAIL = "talentohub2025@gmail.com"
TO_EMAIL = "tu-email@ejemplo.com"  # Cambia esto por tu email

message = Mail(
    from_email=FROM_EMAIL,
    to_emails=TO_EMAIL,
    subject='Prueba de SendGrid',
    plain_text_content='Si recibes este correo, SendGrid está configurado correctamente!'
)

try:
    sg = SendGridAPIClient(API_KEY)
    response = sg.send(message)
    print(f"✅ Correo enviado! Status: {response.status_code}")
    print(f"Response: {response.body}")
except Exception as e:
    print(f"❌ Error: {e}")
```

### Opción 2: Desde Render Shell

1. Ve a tu servicio en Render
2. Click en **"Shell"** en el menú lateral
3. Ejecuta:

```bash
python manage.py shell
```

Luego:

```python
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail
import os

api_key = os.getenv('SENDGRID_API_KEY')
print(f"API Key configurada: {'Sí' if api_key else 'No'}")

message = Mail(
    from_email='talentohub2025@gmail.com',
    to_emails='tu-email@ejemplo.com',  # Cambia esto
    subject='Test desde Render',
    plain_text_content='¡Funciona!'
)

sg = SendGridAPIClient(api_key)
response = sg.send(message)
print(f"Status: {response.status_code}")
```

---

## 🔄 Cómo Funciona Ahora

El código actualizado en `views.py` tiene un sistema de **fallback automático**:

1. **Intenta SMTP primero** (para desarrollo local con Gmail)
   - Si funciona: ✅ Envía por SMTP
   - Si falla: ⬇️ Continúa al paso 2

2. **Usa SendGrid como fallback** (para producción en Render)
   - Si `SENDGRID_API_KEY` está configurada: ✅ Envía por SendGrid API
   - Si no está configurada: ❌ Log de error

### Ventajas:

- ✅ En local: Sigue funcionando con Gmail SMTP (sin cambios)
- ✅ En producción: Usa SendGrid automáticamente
- ✅ Sin cambios de código entre local y producción
- ✅ Logging detallado muestra qué método se usó

---

## 📊 Monitoreo de Correos

Una vez configurado SendGrid, puedes monitorear tus envíos:

1. Ve a **Activity** en SendGrid dashboard
2. Verás todos los correos enviados con su estado:
   - **Delivered**: ✅ Entregado correctamente
   - **Bounced**: ❌ Email inválido
   - **Deferred**: ⏳ Reintentando
   - **Dropped**: 🚫 Bloqueado (por spam, etc.)

---

## 🐛 Troubleshooting

### Error: "The from email does not match a verified Sender Identity"

**Causa**: No has verificado tu Sender Identity en SendGrid.

**Solución**:
1. Ve a Settings → Sender Authentication
2. Verifica que `talentohub2025@gmail.com` esté verificada
3. Si no, completa el proceso de Single Sender Verification

### Error: "Forbidden"

**Causa**: API Key incorrecta o sin permisos.

**Solución**:
1. Genera una nueva API Key en SendGrid
2. Asegúrate de darle permisos de "Mail Send"
3. Actualiza `SENDGRID_API_KEY` en Render

### Los correos no llegan

**Revisa**:
1. **Activity** en SendGrid dashboard → Estado del correo
2. **Spam folder** del destinatario
3. Logs de Render para ver si hay errores

---

## 💰 Límites del Plan Gratuito

- **100 correos/día** permanentemente gratis
- Si necesitas más: $19.95/mes por 50,000 correos
- Para este proyecto, 100/día es más que suficiente

---

## 📝 Resumen de Variables de Entorno Necesarias

En Render Dashboard → Environment:

```bash
# Para SMTP local (opcional en producción)
EMAIL_HOST_USER=talentohub2025@gmail.com
EMAIL_HOST_PASSWORD=ejsu oaiq zivq zdus

# Para SendGrid en producción (REQUERIDO)
SENDGRID_API_KEY=SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Otras variables existentes
SECRET_KEY=...
DEBUG=False
DATABASE_URL=...
SUPABASE_URL=...
SUPABASE_SERVICE_KEY=...
```

---

## ✅ Checklist Final

- [ ] Cuenta de SendGrid creada
- [ ] API Key generada y copiada
- [ ] Single Sender verificado (talentohub2025@gmail.com)
- [ ] `SENDGRID_API_KEY` agregada a Render Environment
- [ ] Código actualizado y pusheado a GitHub
- [ ] Render redeployado
- [ ] Prueba de postulación realizada
- [ ] Correo recibido exitosamente
- [ ] Logs de Render muestran `✅ [SendGrid] Correo enviado`

Una vez completado todo esto, los correos funcionarán perfectamente tanto en local como en producción. 🎉
