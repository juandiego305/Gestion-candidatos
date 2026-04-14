# Configuración de Gunicorn para producción
import multiprocessing
import os

# Dirección de escucha
bind = "0.0.0.0:8000"

# Número de workers (2-4 x núcleos de CPU)
# En Render, demasiados workers pueden causar OOM; permitir override por entorno.
workers = int(os.getenv("WEB_CONCURRENCY", "2"))

# Tipo de workers (sync es el predeterminado, pero puedes usar gevent para async)
worker_class = "sync"

# Timeout para requests (con override por entorno)
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))

# Timeout para mantener conexiones keep-alive
keepalive = 5

# Timeout para workers silenciosos
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "120"))

# Nivel de log
loglevel = "info"

# Archivo de log de accesos
accesslog = "-"  # stdout

# Archivo de log de errores
errorlog = "-"  # stderr

# Capturar salida de la aplicación en logs
capture_output = True

# Habilitar logging de acceso
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Límite de memoria (opcional, descomenta si necesitas)
# max_requests = 1000  # Reiniciar worker después de N requests (previene memory leaks)
# max_requests_jitter = 50

# Preload de la aplicación (mejora rendimiento pero usa más memoria)
preload_app = False

# Threads por worker (solo si usas gthread como worker_class)
# threads = 2
