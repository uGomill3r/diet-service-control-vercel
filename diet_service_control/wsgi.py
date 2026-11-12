"""
WSGI application para despliegue en Vercel (detecta `application` vía WSGI_APPLICATION).
"""
import os
from django.core.wsgi import get_wsgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "diet_service_control.settings")

application = get_wsgi_application()
