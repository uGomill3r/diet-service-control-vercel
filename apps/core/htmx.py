"""
Utilidades para respuestas parciales con HTMX.
"""
import logging
from django.shortcuts import render
from django.utils.cache import patch_vary_headers

logger = logging.getLogger(__name__)


def es_htmx(request):
    """True si la petición la envió HTMX (cabecera HX-Request)."""
    return request.headers.get("HX-Request") == "true"


def render_page_or_partial(request, pagina, parcial, contexto, status=200):
    """
    Devuelve el parcial si la petición viene de HTMX y la página completa si no.
    Agrega 'Vary: HX-Request' para que ninguna caché mezcle ambas respuestas.
    """
    plantilla = parcial if es_htmx(request) else pagina
    logger.debug("Renderizando %s (htmx=%s)", plantilla, es_htmx(request))
    respuesta = render(request, plantilla, contexto, status=status)
    patch_vary_headers(respuesta, ["HX-Request"])
    return respuesta
