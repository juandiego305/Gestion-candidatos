from datetime import datetime, timedelta
from django.conf import settings
from django.core.mail import send_mail
from django.http import JsonResponse
import logging

logger = logging.getLogger(__name__)

# Diccionario temporal en memoria
FAILED_LOGINS = {}

class LoginSecurityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # Verificar bloqueo ANTES de procesar la request
        if request.path.endswith('/login/') and request.method == 'POST':
            username = request.POST.get('username')
            if username:
                block_response = self._check_if_blocked(username)
                if block_response:
                    return block_response
        
        response = self.get_response(request)
        
        # Verificar intento fallido DESPUÉS de la respuesta
        if (request.path.endswith('/login/') and 
            request.method == 'POST' and 
            response.status_code in [400, 401, 403]):
            
            self._handle_login_attempt(request, response, username)
        
        return response

    def _check_if_blocked(self, username):
        """Verifica si el usuario está bloqueado antes del login"""
        self._clean_old_attempts()
        
        data = FAILED_LOGINS.get(username)
        if data and data.get("lock_until"):
            now = datetime.now()
            if now < data["lock_until"]:
                return self._block_user_response(username, data["lock_until"])
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
            FAILED_LOGINS[username]["count"] += 1
            FAILED_LOGINS[username]["last_attempt"] = now
            
            if FAILED_LOGINS[username]["count"] >= max_attempts:
                FAILED_LOGINS[username]["lock_until"] = now + timedelta(minutes=lock_minutes)
                logger.warning(f"Usuario {username} BLOQUEADO por {lock_minutes} minutos")
        else:
            FAILED_LOGINS[username] = {
                "count": 1,
                "last_attempt": now,
                "lock_until": None
            }

    def _clean_old_attempts(self):
        """Limpia intentos fallidos antiguos"""
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        
        expired_users = [
            username for username, data in FAILED_LOGINS.items()
            if data["last_attempt"] < one_hour_ago and not data.get("lock_until")
        ]
        
        for username in expired_users:
            FAILED_LOGINS.pop(username, None)

    def _block_user_response(self, username, lock_until):
        """Respuesta cuando el usuario está bloqueado"""
        remaining_time = lock_until - datetime.now()
        minutes_remaining = max(1, int(remaining_time.total_seconds() / 60))
        
        # Intentar enviar email (deberías obtener el email real de la base de datos)
        try:
            # Esto es un placeholder - necesitas obtener el email del usuario
            user_email = f"{username}@example.com"  # Reemplazar con lógica real
            send_mail(
                subject="🔒 Cuenta bloqueada temporalmente",
                message=f"""Hola,

Tu cuenta ha sido bloqueada temporalmente debido a múltiples intentos fallidos de acceso.

El bloqueo se levantará automáticamente en {minutes_remaining} minutos.

Si no fuiste tú, por favor contacta al administrador.

Saludos,
Sistema de Gestión de Candidatos""",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user_email],
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"Error enviando email de bloqueo: {e}")
        
        return JsonResponse({
            "detail": f"Cuenta temporalmente bloqueada. Demasiados intentos fallidos. Intenta nuevamente en {minutes_remaining} minutos.",
            "blocked_until": lock_until.isoformat(),
            "remaining_minutes": minutes_remaining
        }, status=403)