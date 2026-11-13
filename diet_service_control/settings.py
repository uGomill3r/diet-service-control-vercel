"""
Configuración principal del proyecto DietServiceControl.
Compatible con Django 5.2 + PostgreSQL (Neon) y despliegue serverless en Vercel.
"""
import os
from pathlib import Path
from urllib.parse import parse_qsl, unquote, urlparse

from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

# Entorno de ejecución: Vercel inyecta VERCEL=1 automáticamente
IS_VERCEL = os.environ.get("VERCEL") == "1"


def _env_list(name, default=""):
    """Lee una variable de entorno separada por comas y devuelve una lista limpia."""
    return [item.strip() for item in os.environ.get(name, default).split(",") if item.strip()]


# Seguridad
_DEFAULT_SECRET_KEY = "django-insecure-cambia-esto-en-produccion"
SECRET_KEY = os.environ.get("SECRET_KEY", _DEFAULT_SECRET_KEY)
if IS_VERCEL and SECRET_KEY == _DEFAULT_SECRET_KEY:
    # Evita desplegar en producción con la clave por defecto
    raise ImproperlyConfigured("Define la variable de entorno SECRET_KEY en Vercel.")

DEBUG = os.environ.get("DEBUG", "False") == "True"

# Dominios que Vercel asigna al despliegue (sin esquema). Se usan para hosts y CSRF.
_vercel_hosts = [
    host
    for host in (
        os.environ.get("VERCEL_URL"),
        os.environ.get("VERCEL_BRANCH_URL"),
        os.environ.get("VERCEL_PROJECT_PRODUCTION_URL"),
    )
    if host
]

# Para un dominio propio, agregarlo en ALLOWED_HOSTS y CSRF_TRUSTED_ORIGINS (variables de entorno)
ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS", "localhost,127.0.0.1") + _vercel_hosts
CSRF_TRUSTED_ORIGINS = _env_list("CSRF_TRUSTED_ORIGINS") + [
    f"https://{host}" for host in _vercel_hosts
]

if IS_VERCEL:
    # Vercel termina el TLS en su proxy: Django debe confiar en el encabezado reenviado
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True

# Aplicaciones
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Apps propias
    "apps.core",
    "apps.auth_app",
    "apps.dashboard",
    "apps.dia",
    "apps.pagos",
    "apps.reportes",
    "apps.log",
    "apps.importar",
    "apps.validacion",
    "apps.calendario",
]

# Messages backend para sesiones sin django.contrib.auth completo
MESSAGE_STORAGE = "django.contrib.messages.storage.session.SessionStorage"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "diet_service_control.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.jinja2.Jinja2",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": False,
        "OPTIONS": {
            "environment": "diet_service_control.jinja2.environment",
            # Inyecta 'request', 'user', 'messages' en cada template
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "diet_service_control.wsgi.application"


def _database_from_url(url):
    """
    Convierte una cadena de conexión (DATABASE_URL de Neon) en la configuración de Django.
    Usa la URL con pooler (host '-pooler'): PgBouncer en modo transacción, por eso
    se desactivan los cursores del lado del servidor y las conexiones persistentes.
    """
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query))
    options = {"sslmode": query.get("sslmode", "require")}
    if "channel_binding" in query:
        options["channel_binding"] = query["channel_binding"]
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/"),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "",
        "PORT": str(parsed.port or 5432),
        "CONN_MAX_AGE": 0,  # serverless: no reutilizar conexiones entre invocaciones
        "DISABLE_SERVER_SIDE_CURSORS": True,  # requerido por el pooler de Neon
        "OPTIONS": options,
    }


# Base de datos PostgreSQL: DATABASE_URL (Neon) o variables DB_* para desarrollo local
_database_url = os.environ.get("DATABASE_URL")
if _database_url:
    DATABASES = {"default": _database_from_url(_database_url)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.environ.get("DB_NAME", "diet_service_control"),
            "USER": os.environ.get("DB_USER", "postgres"),
            "PASSWORD": os.environ.get("DB_PASSWORD", "postgres"),
            "HOST": os.environ.get("DB_HOST", "localhost"),
            "PORT": os.environ.get("DB_PORT", "5432"),
        }
    }

# Internacionalización
LANGUAGE_CODE = "es-pe"
TIME_ZONE = "America/Lima"
USE_I18N = True
USE_TZ = True

# Archivos estáticos: Vercel ejecuta collectstatic en el build (por STATIC_ROOT)
# y los sirve desde su CDN en STATIC_URL. En local, runserver con DEBUG=True los sirve.
STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Sesiones almacenadas en la base de datos
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_AGE = 86400  # 24 horas

# Credencial de administrador desde variables de entorno
APP_USER = os.environ.get("APP_USER", "admin")
APP_PASSWORD = os.environ.get("APP_PASSWORD", "admin123")

# Logging (en Vercel la consola queda en los logs de la función)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} {module} {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": os.environ.get("DJANGO_LOG_LEVEL", "INFO"),
            "propagate": False,
        },
        "apps": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
