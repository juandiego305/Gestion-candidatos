from datetime import datetime, timedelta
from django.conf import settings
from django.http import JsonResponse
from django.contrib.auth import get_user_model
import json
import logging
from .email_service import send_template_email

logger = logging.getLogger(__name__)

# Diccionario temporal en memoria (NOTA: usar Redis/Cache en producción)
FAILED_LOGINS = {}


class LoginSecurityMiddleware:
    """Middleware para limitar intentos de inicio de sesión.

    Mejoras realizadas:
    - Soporta endpoints de Simple JWT (/api/token/) en formato JSON.
    - Extrae 'username' o 'email' desde JSON body cuando aplica.
    - Intenta obtener el email real del usuario desde el modelo User para notificaciones.
    - No bloquea el flujo si ocurre un error en la lógica de notificación.
    - WARNING: Sigue usando almacenamiento en memoria; para producción usar Redis o cache compartida.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Determinar si la ruta de login corresponde (ej. SimpleJWT)
        is_login_path = request.path.endswith('/api/token/') or request.path.endswith('/login/')
        username = None

        # Verificar bloqueo ANTES de procesar la request
        if is_login_path and request.method == 'POST':
            username = self._extract_username_from_request(request)
            if username:
                block_response = self._check_if_blocked(username)
                if block_response:
                    return block_response

        response = self.get_response(request)

        # Verificar intento fallido DESPUÉS de la respuesta
        if is_login_path and request.method == 'POST' and response.status_code in (400, 401, 403):
            # Si no se extrajo antes, intentar ahora
            if not username:
                username = self._extract_username_from_request(request)
            self._handle_login_attempt(request, response, username)

        return response

    def _extract_username_from_request(self, request):
        """Extrae el username/email del body POST (soporta form-data y JSON)."""
        try:
            # Primero probar form data
            username = request.POST.get('username') or request.POST.get('email')
            if username:
                return username

            # Si no hay form data, intentar JSON
            if request.content_type and 'application/json' in request.content_type:
                try:
                    body = request.body.decode('utf-8')
                    if not body:
                        return None
                    data = json.loads(body)
                    return data.get('username') or data.get('email')
                except Exception:
                    return None
        except Exception:
            return None
        return None

    def _check_if_blocked(self, username):
        """Verifica si el usuario está bloqueado antes del login"""
        self._clean_old_attempts()

        data = FAILED_LOGINS.get(username)
        if data and data.get('lock_until'):
            now = datetime.now()
            if now < data['lock_until']:
                return self._block_user_response(username, data['lock_until'])
            else:
                # Desbloquear si ya pasó el tiempo
                FAILED_LOGINS.pop(username, None)
        return None

    def _handle_login_attempt(self, request, response, username):
        """Maneja el resultado del intento de login"""
        if username and response.status_code != 200:
            # Si no fue exitoso, registrar intento fallido
            self._record_failed_attempt(username)
        elif username and response.status_code == 200:
            # Si fue exitoso, limpiar intentos fallidos
            FAILED_LOGINS.pop(username, None)

    def _record_failed_attempt(self, username):
        """Registra un intento fallido de login"""
        now = datetime.now()
        max_attempts = getattr(settings, 'MAX_FAILED_LOGINS', 3)
        lock_minutes = getattr(settings, 'ACCOUNT_LOCK_MINUTES', 5)

        if username in FAILED_LOGINS:
            FAILED_LOGINS[username]['count'] += 1
            FAILED_LOGINS[username]['last_attempt'] = now

            if FAILED_LOGINS[username]['count'] >= max_attempts:
                FAILED_LOGINS[username]['lock_until'] = now + timedelta(minutes=lock_minutes)
                logger.warning(f'Usuario {username} BLOQUEADO por {lock_minutes} minutos')
        else:
            FAILED_LOGINS[username] = {
                'count': 1,
                'last_attempt': now,
                'lock_until': None,
            }

    def _clean_old_attempts(self):
        """Limpia intentos fallidos antiguos"""
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)

        expired_users = [
            username for username, data in list(FAILED_LOGINS.items())
            if data['last_attempt'] < one_hour_ago and not data.get('lock_until')
        ]

        for username in expired_users:
            FAILED_LOGINS.pop(username, None)

    def _block_user_response(self, username, lock_until):
        """Respuesta cuando el usuario está bloqueado"""
        remaining_time = lock_until - datetime.now()
        minutes_remaining = max(1, int(remaining_time.total_seconds() / 60))

        # Intentar enviar email real del usuario si existe
        try:
            User = get_user_model()
            user = User.objects.filter(username=username).first() or User.objects.filter(email=username).first()
            user_email = user.email if user else f'{username}@example.com'
            send_template_email(
                template_key='account_locked',
                recipient_list=[user_email],
                context={'minutes_remaining': minutes_remaining},
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f'Error enviando email de bloqueo: {e}')

        return JsonResponse({
            'detail': (
                f'Cuenta temporalmente bloqueada. Demasiados intentos fallidos. Intenta nuevamente en {minutes_remaining} minutos.'
            ),
            'blocked_until': lock_until.isoformat(),
            'remaining_minutes': minutes_remaining,
        }, status=403)


# ════════════════════════════════════════════════════════════════════════════
# PERMISSION CLASS PARA VALIDAR INACTIVIDAD
# ════════════════════════════════════════════════════════════════════════════

from rest_framework.permissions import BasePermission
from rest_framework.exceptions import AuthenticationFailed

class CheckUserInactivityPermission(BasePermission):
    """
    Permission class que valida la inactividad del usuario.
    
    Se ejecuta DESPUÉS de la autenticación JWT, así que request.user es confiable.
    Si el usuario no ha hecho ninguna solicitud en los últimos N segundos, rechaza con 401.
    """
    
    def has_permission(self, request, view):
        # Solo validar para usuarios autenticados
        if not request.user or not request.user.is_authenticated:
            return True  # Dejar que otros permisos manejen anónimos
        
        from django.core.cache import cache
        from django.utils import timezone
        from datetime import datetime
        
        inactivity_timeout = getattr(settings, 'INACTIVITY_TIMEOUT', 120)
        # Mantener el registro de actividad más tiempo que el timeout de inactividad,
        # para poder detectar expiración al siguiente request.
        activity_cache_ttl = getattr(settings, 'INACTIVITY_CACHE_TTL', 86400)
        cache_key = f'user_activity_{request.user.id}'
        
        # Verificar última actividad
        last_activity = cache.get(cache_key)
        
        if last_activity is None:
            # Primera vez o cache expiró - registrar actividad
            cache.set(cache_key, timezone.now().isoformat(), activity_cache_ttl)
            return True
        
        try:
            last_activity_dt = last_activity if isinstance(last_activity, datetime) else datetime.fromisoformat(last_activity)
            current_time = timezone.now()
            time_elapsed = (current_time - last_activity_dt).total_seconds()
            
            if time_elapsed > inactivity_timeout:
                # Usuario inactivo - rechazar
                logger.warning(
                    f'Usuario {request.user.username} rechazado por inactividad. '
                    f'Tiempo sin actividad: {time_elapsed:.0f}s (timeout: {inactivity_timeout}s)'
                )
                msg = f'Tu sesión ha expirado por inactividad (sin actividad por {int(time_elapsed)}s).'
                raise AuthenticationFailed({
                    'error_code': 'SESSION_TIMEOUT',
                    'detail': msg
                })
            
            # Renovar timestamp de actividad
            cache.set(cache_key, timezone.now().isoformat(), activity_cache_ttl)
            return True
            
        except AuthenticationFailed:
            raise
        except Exception as e:
            logger.error(f'Error validando inactividad: {e}')
            return True  # Permitir si hay error, no romper la app
