# 📧 Configuración de SendGrid para envío de correos en Render

## ❌ Problema Actual
Render bloquea el puerto 587 de Gmail (error: `Network is unreachable`), por lo que los correos no se pueden enviar usando Gmail SMTP.

## ✅ Solución: Usar SendGrid (GRATIS hasta 100 correos/día)

### 1️⃣ Crear cuenta en SendGrid

1. Ve a https://signup.sendgrid.com/
2. Regístrate con tu correo (puedes usar `talentohub2025@gmail.com`)
3. Completa el formulario de registro
4. Verifica tu email

### 2️⃣ Crear API Key en SendGrid

1. Inicia sesión en https://app.sendgrid.com/
2. Ve a **Settings** → **API Keys** (menú lateral izquierdo)
3. Click en **"Create API Key"**
4. Configuración:
   - **API Key Name**: `TalentoHub-Render-Production`
   - **API Key Permissions**: **Full Access** (o "Restricted Access" con permisos de Mail Send)
5. Click en **"Create & View"**
6. **COPIA LA API KEY** (solo se muestra una vez):
   ```
   SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
7. Guárdala en un lugar seguro

### 3️⃣ Verificar Sender Identity (Remitente)

SendGrid requiere verificar tu email antes de enviar:

1. En SendGrid, ve a **Settings** → **Sender Authentication**
2. Opción A - **Single Sender Verification** (más rápido):
   - Click en **"Verify a Single Sender"**
   - Email: `talentohub2025@gmail.com`
   - From Name: `TalentoHub - Gestión de Candidatos`
   - Reply To: `talentohub2025@gmail.com`
   - Company: `TalentoHub`
   - Address, City, etc. (completa el formulario)
   - Click en **"Create"**
   - **Verifica el email** que SendGrid te envía a `talentohub2025@gmail.com`

3. Opción B - **Domain Authentication** (más profesional pero complejo):
   - Requiere tener tu propio dominio
   - No recomendado para empezar

### 4️⃣ Agregar API Key a Render

1. Ve a https://dashboard.render.com
2. Selecciona tu servicio: `gestion-candidatos-1`
3. Ve a la pestaña **Environment**
4. Click en **"Add Environment Variable"**
5. Agrega:
   ```
   Key: SENDGRID_API_KEY
   Value: SG.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   ```
   (pega tu API key completa)
6. Click en **"Save Changes"**
7. Render redesplegará automáticamente (2-3 minutos)

### 5️⃣ Verificar que funciona

Después del redespliegue:

1. Ve a los **Logs** de Render
2. Busca mensajes de inicio que digan:
   ```
   ✅ Usando SendGrid para envío de correos
   ```

3. Haz una postulación de prueba desde el frontend
4. Busca en los logs:
   ```
   📧 Enviando correo de postulación a usuario@ejemplo.com
   ✅ Correo enviado exitosamente a usuario@ejemplo.com
   ```

5. Verifica tu bandeja de entrada del correo del candidato

### 6️⃣ Monitoreo de correos enviados

En SendGrid Dashboard puedes ver:
- **Activity** → Email Activity: ver todos los correos enviados, entregados, rebotados
- Estadísticas de entrega
- Errores de envío

## 🔄 Fallback a Gmail (si no configuras SendGrid)

Si NO agregas `SENDGRID_API_KEY` en Render, el sistema intentará usar Gmail SMTP (pero probablemente falle por el bloqueo de puerto).

## 📊 Límites de SendGrid Free

- **100 correos por día** (suficiente para empezar)
- Si necesitas más, puedes:
  - Upgrade a plan de pago ($15/mes = 40,000 correos)
  - O usar otro servicio como Amazon SES, Mailgun, etc.

## ⚠️ Importante

1. **NO compartas tu API Key públicamente** (es como una contraseña)
2. **Verifica tu sender email** en SendGrid antes de enviar
3. Si cambias el `DEFAULT_FROM_EMAIL`, asegúrate de verificarlo en SendGrid primero
4. Los correos llegarán más rápido con SendGrid que con Gmail SMTP

## 🆘 Troubleshooting

**Error: "The from email does not match a verified Sender Identity"**
- Solución: Ve a SendGrid → Settings → Sender Authentication y verifica tu email

**Error: "Forbidden"**
- Solución: Verifica que tu API Key tenga permisos de "Mail Send"

**Correos no llegan:**
- Revisa SendGrid → Activity para ver el estado del correo
- Verifica spam/junk en la bandeja del destinatario
- Confirma que el email del destinatario sea válido
