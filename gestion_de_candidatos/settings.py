from pathlib import Path
import os
from dotenv import load_dotenv
import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

SECRET_KEY = 'django-insecure-ud!hdb+@vw&y^omt70y6wzrma%e)#px4f#sf03ja!zfbh10f@t'
DEBUG = True
ALLOWED_HOSTS = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "core",
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",

    # --- Middleware personalizado para control de intentos fallidos y bloqueo temporal ---
    # (crearemos el archivo core/middleware.py)
    "core.middleware.LoginSecurityMiddleware",
]

ROOT_URLCONF = "gestion_de_candidatos.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "gestion_de_candidatos.wsgi.application"

# Prueba con nueva config: postgresql://postgres:4sLsg873jktoN3vn@db.fkpjhyjcexhhbljexrbb.supabase.co:5432/postgres
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': "postgres",
        'USER': "postgres",
        'PASSWORD': "4sLsg873jktoN3vn", 
        'HOST': "db.fkpjhyjcexhhbljexrbb.supabase.co",
        'PORT': "5432",
        
    }
}

"""

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': BASE_DIR / 'db.sqlite3',
    }
}

"""

# 🔒 CONFIGURACIÓN DE SEGURIDAD Y POLÍTICAS DE CONTRASEÑAS

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 8},  # Requiere mínimo 8 caracteres
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]


# 🕒 CONFIGURACIÓN DE SESIÓN E INACTIVIDAD

# Cierra sesión automáticamente después de 15 minutos de inactividad
SESSION_COOKIE_AGE = 900  # 15 minutos (en segundos)
SESSION_SAVE_EVERY_REQUEST = True  # reinicia el contador con cada acción
SESSION_EXPIRE_AT_BROWSER_CLOSE = True


# 🚫 BLOQUEO TEMPORAL TRAS INTENTOS FALLIDOS

# Se implementará en core/middleware.py
# Esta sección permite definir la política
MAX_FAILED_LOGINS = 3           # número máximo de intentos
ACCOUNT_LOCK_MINUTES = 5        # minutos de bloqueo temporal


# ✉️ CONFIGURACIÓN OPCIONAL DE CORREO

# Para enviar notificaciones de bloqueo al usuario
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = "smtp.gmail.com"
EMAIL_PORT = 587
EMAIL_USE_TLS = True
EMAIL_HOST_USER = os.getenv("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.getenv("EMAIL_HOST_PASSWORD", "")
DEFAULT_FROM_EMAIL = EMAIL_HOST_USER


# 🌐 OTROS PARÁMETROS GENERALES

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
# "Ya se termino la fase de prueba con core.Usuario ahora se volvera a usar auth_user"  AUTH_USER_MODEL = "core.Usuario"
