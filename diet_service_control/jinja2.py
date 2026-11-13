"""
Entorno Jinja2 personalizado para Django 5.2.
Expone: url_for, static, csrf_input, csrf_token, request como globales.

En Jinja2 con Django el tag {% csrf_token %} no existe nativo.
Se reemplaza con {{ csrf_input }} (genera el <input hidden>) o
{{ csrf_token }} (genera solo el valor del token).
Los templates usan {% csrf_token %} — lo implementamos como una Extension
que genera el input directamente.
"""
import logging
from jinja2 import Environment, nodes
from jinja2.ext import Extension
from django.urls import reverse
from django.templatetags.static import static
from django.middleware.csrf import get_token

logger = logging.getLogger(__name__)


class CsrfExtension(Extension):
    """
    Extensión Jinja2 que implementa {% csrf_token %} compatible con Django.
    Genera <input type="hidden" name="csrfmiddlewaretoken" value="TOKEN">.
    """
    tags = {"csrf_token"}

    def parse(self, parser):
        lineno = next(parser.stream).lineno
        call = self.call_method("_render_csrf", [nodes.Name("request", "load")])
        return nodes.Output([call], lineno=lineno)

    def _render_csrf(self, request):
        from django.middleware.csrf import get_token
        from markupsafe import Markup
        token = get_token(request)
        return Markup(f'<input type="hidden" name="csrfmiddlewaretoken" value="{token}">')


def csrf_value(request):
    """Devuelve solo el valor del token CSRF (para hx-headers de HTMX)."""
    return get_token(request)


def environment(**options):
    """Configura el entorno Jinja2 con las utilidades necesarias."""
    logger.debug("Inicializando entorno Jinja2 personalizado")
    options.setdefault("extensions", [])
    options["extensions"] = list(options["extensions"]) + [CsrfExtension]
    env = Environment(**options)
    env.globals.update(
        {
            "url_for": url_for_django,
            "static": static,
            "csrf_value": csrf_value,
        }
    )
    return env


def url_for_django(endpoint, **kwargs):
    """
    Reemplaza url_for de Flask.
    Convierte 'modulo.vista' a nombre de URL de Django.
    """
    endpoint_map = {
        "auth.login": "login",
        "auth.logout": "logout",
        "auth.recuperar": "recuperar",
        "auth.cambiar_clave": "cambiar_clave",
        "dashboard.dashboard": "dashboard",
        "dia.ver_dia": "ver_dia",
        "dia.editar_dia": "editar_dia",
        "pagos.pagos": "pagos",
        "pagos.editar_pago": "editar_pago",
        "reportes.reporte_ciclo": "reporte_ciclo",
        "log.log": "log",
        "validacion.hoy": "hoy",
        "validacion.obs_entrega": "obs_entrega",
        "calendario.calendario": "calendario",
        "calendario.modal_dia": "modal_dia",
        "calendario.guardar_dia": "guardar_dia",
        "validacion.marcar_entrega": "marcar_entrega",
        "validacion.validar_hasta_ayer": "validar_hasta_ayer",
        "static": "static",
    }

    django_name = endpoint_map.get(endpoint, endpoint)

    if django_name == "static":
        filename = kwargs.get("filename", "")
        return static(filename)

    try:
        return reverse(django_name, kwargs=kwargs if kwargs else None)
    except Exception:
        return reverse(django_name)
