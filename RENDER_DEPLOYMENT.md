# Instrucciones de Deployment en Render.com

## Configuración del Start Command

En Render.com, configura el **Start Command** como:

```bash
gunicorn -c gunicorn_config.py gestion_de_candidatos.wsgi:application
```

**O si prefieres especificar los parámetros directamente:**

```bash
gunicorn gestion_de_candidatos.wsgi:application --bind 0.0.0.0:8000 --workers 4 --timeout 120 --graceful-timeout 120 --log-level info
```

## Variables de Entorno Requeridas

Configura estas variables en Render Dashboard → Environment:

```
SECRET_KEY=django-insecure-ud!hdb+@vw&y^omt70y6wzrma%e)#px4f#sf03ja!zfbh10f@t
DEBUG=False
ALLOWED_HOSTS=gestion-candidatos-1.onrender.com,.onrender.com,localhost

DATABASE_URL=postgresql://postgres:4sLsg873jktoN3vn@db.fkpjhyjcexhhbljexrbb.supabase.co:5432/postgres

SUPABASE_URL=https://fkpjhyjcexhhbljexrbb.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImZrcGpoeWpjZXhoaGJsamV4cmJiIiwicm9sZSI6InNlcnZpY2Vfcm9sZSIsImlhdCI6MTczMjY2NDM1MywiZXhwIjoyMDQ4MjQwMzUzfQ.qM5x4V0W2rWTW6pI4wRGOMuPy13l9SN4ZnHk7IqaC4w

EMAIL_HOST_PASSWORD=ejsu oaiq zivq zdus

PYTHON_VERSION=3.11.0
```

## Solución de Problemas Comunes

### Error 504 Gateway Timeout

**Causa:** Las operaciones (subida de archivos, envío de correos) tardan más de 30 segundos.

**Solución aplicada:**
1. ✅ Aumentado timeout de gunicorn a 120 segundos
2. ✅ Optimizado subida de archivos con timeout reducido (15s)
3. ✅ Configurado `fail_silently=True` en envío de correos
4. ✅ El correo no bloquea la respuesta al usuario

### Error 409 Duplicate (Supabase Storage)

**Causa:** Intentar subir un archivo que ya existe.

**Solución aplicada:**
1. ✅ Agregado `"upsert": "true"` para sobrescribir archivos existentes
2. ✅ Validación anticipada de postulaciones duplicadas

### Worker Timeout / Out of Memory

**Causa:** Workers de gunicorn son terminados por timeout o memoria insuficiente.

**Solución aplicada:**
1. ✅ Configurado `timeout = 120` en gunicorn_config.py
2. ✅ Configurado `graceful_timeout = 120` para shutdown limpio
3. ✅ Optimizado número de workers según CPU disponible

## Verificación Post-Deploy

Después de hacer deploy, verifica:

1. **Health check:** `https://gestion-candidatos-1.onrender.com/api/`
2. **Login:** `POST https://gestion-candidatos-1.onrender.com/api/auth/login/`
3. **Vacantes:** `GET https://gestion-candidatos-1.onrender.com/api/vacantes/`
4. **Postular:** `POST https://gestion-candidatos-1.onrender.com/vacantes/{id}/postular/`

## Logs en Render

Para ver los logs en tiempo real:
1. Ve a tu servicio en Render Dashboard
2. Click en "Logs" en el menú lateral
3. Busca errores con `[ERROR]` o `[CRITICAL]`

## Optimizaciones Aplicadas

### En `views.py`:
- ✅ Validación de postulaciones duplicadas ANTES de procesar archivos
- ✅ Timeout reducido para subida a Supabase (15s)
- ✅ `fail_silently=True` en envío de correos
- ✅ Logging mejorado con `logger.warning` en lugar de `logger.error`

### En `gunicorn_config.py`:
- ✅ Timeout aumentado a 120 segundos
- ✅ Workers dinámicos según CPU: `cpu_count * 2 + 1`
- ✅ Graceful timeout de 120 segundos
- ✅ Logging mejorado con formato detallado

## Próximos Pasos (Opcional)

Para mejorar aún más el rendimiento:

1. **Cola de tareas asíncrona (Celery + Redis):**
   - Enviar correos en background
   - No bloquear la respuesta HTTP

2. **Compresión de archivos:**
   - Comprimir CVs antes de subirlos
   - Validar tamaño máximo (ej: 5MB)

3. **CDN para archivos estáticos:**
   - Usar Cloudflare o similar
   - Reducir carga en el servidor

4. **Caché de base de datos:**
   - Usar Redis para cachear vacantes publicadas
   - Reducir queries a Supabase
