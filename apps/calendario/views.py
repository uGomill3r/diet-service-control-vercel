"""
Calendario unificado (semana/mes) y modal de edición del pedido de un día.
"""
import json
import logging
from datetime import date

from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.core.decorators import protegido
from apps.core.htmx import es_htmx, render_page_or_partial
from . import services

logger = logging.getLogger(__name__)


def _fecha_iso(valor):
    """Parsea YYYY-MM-DD; devuelve None si es inválida."""
    try:
        return date.fromisoformat(valor or "")
    except ValueError:
        return None


@protegido
@require_GET
def calendario(request):
    """Calendario con toggle semana/mes; devuelve solo el parcial si llega de HTMX."""
    hoy = timezone.localdate()
    vista = request.GET.get("vista", "semana")
    if vista not in ("semana", "mes"):
        vista = "semana"
    ancla = _fecha_iso(request.GET.get("fecha")) or hoy
    datos = services.construir_mes(ancla, hoy) if vista == "mes" else services.construir_semana(ancla, hoy)
    ctx = {
        "vista": vista,
        "url_actual": f"{reverse('calendario')}?vista={vista}&fecha={datos['ancla']}",
        **datos,
    }
    return render_page_or_partial(request, "calendario.html", "partials/_calendario.html", ctx)


@protegido
@require_GET
def modal_dia(request):
    """Contenido del <dialog> de un día. Sin HTMX redirige a la edición completa."""
    fecha = _fecha_iso(request.GET.get("fecha"))
    if fecha is None:
        logger.warning("Modal de día con fecha inválida: %s", request.GET.get("fecha"))
        return HttpResponseBadRequest("Fecha inválida")
    if not es_htmx(request):
        return redirect(f"{reverse('editar_dia')}?fecha={fecha.strftime('%d-%m-%Y')}")
    return render_page_or_partial(
        request, "partials/_modal_dia.html", "partials/_modal_dia.html", services.datos_modal(fecha)
    )


@protegido
@require_POST
def guardar_dia(request):
    """Guarda el pedido del día y pide cerrar el modal y refrescar el calendario."""
    fecha = _fecha_iso(request.POST.get("fecha"))
    if fecha is None:
        logger.warning("Guardar día con fecha inválida: %s", request.POST.get("fecha"))
        return HttpResponseBadRequest("Fecha inválida")
    try:
        services.guardar_pedido(fecha, request.POST)
    except Exception:
        logger.error("Error al guardar el pedido de %s", fecha, exc_info=True)
        return HttpResponse("No se pudo guardar", status=500)
    respuesta = HttpResponse(status=204)
    respuesta["HX-Trigger"] = json.dumps({"cerrarModal": True, "calendarioActualizado": True})
    return respuesta
