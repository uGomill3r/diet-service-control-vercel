"""
Vistas de la pantalla Hoy (validación de entregas, pensada para móvil).
"""
import json
import logging
from datetime import date
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from apps.core.decorators import protegido
from apps.core.models import Entrega
from apps.core.htmx import es_htmx, render_page_or_partial
from apps.core.utils import formatear_fecha_con_dia
from . import services

logger = logging.getLogger(__name__)


def _contexto_lista(hoy, oob=False):
    """Contexto compartido por la página Hoy y sus parciales."""
    pedidos, entregas = services.cargar_estado()
    dia_hoy, pendientes, validados = services.armar_dias(pedidos, entregas, hoy)
    ctx = {
        "hoy_etiqueta": formatear_fecha_con_dia(hoy),
        "dia_hoy": dia_hoy,
        "pendientes": pendientes,
        "validados": validados,
        "hay_masivo": any(not d["observaciones"] for d in pendientes),
        "oob": oob,
    }
    ctx.update(services.calcular_contadores(pedidos, entregas, hoy))
    return ctx


@protegido
@require_GET
def hoy(request):
    """Pantalla de inicio: pendientes de validación de hoy y días anteriores."""
    ctx = _contexto_lista(services.hoy_lima())
    return render_page_or_partial(request, "hoy.html", "partials/_lista_hoy.html", ctx)


@protegido
@require_POST
def marcar_entrega(request):
    """Fija la entrega (valor explícito 1/0). Devuelve el botón y los contadores (OOB)."""
    try:
        fecha = date.fromisoformat(request.POST.get("fecha", ""))
        valor = int(request.POST.get("valor", ""))
    except ValueError:
        logger.warning("Marcar entrega con datos inválidos: %s", dict(request.POST))
        return HttpResponseBadRequest("Datos inválidos")
    tipo = request.POST.get("tipo", "")
    if valor not in (0, 1):
        logger.warning("Valor de entrega inválido: %s", valor)
        return HttpResponseBadRequest("Valor inválido")

    hoy_d = services.hoy_lima()
    try:
        services.guardar_entrega(fecha, tipo, valor, hoy_d)
    except services.EntregaNoValida as exc:
        logger.warning("Entrega rechazada: %s", exc)
        return HttpResponseBadRequest(str(exc))
    except Exception:
        logger.error("Error al guardar entrega %s %s", tipo, fecha, exc_info=True)
        return HttpResponse("No se pudo guardar", status=500)

    if not es_htmx(request):
        return redirect(reverse("hoy"))

    pedidos, entregas = services.cargar_estado()
    ctx = {
        "iso": fecha.isoformat(),
        "tipo": tipo,
        "titulo": tipo.capitalize(),
        "entregado": bool(valor),
        "oob": True,
    }
    ctx.update(services.calcular_contadores(pedidos, entregas, hoy_d))
    return render_page_or_partial(
        request, "partials/_respuesta_marcar.html", "partials/_respuesta_marcar.html", ctx
    )


@protegido
@require_POST
def validar_hasta_ayer(request):
    """Marca como entregados los pedidos anteriores a hoy (excepto con observaciones)."""
    hoy_d = services.hoy_lima()
    try:
        services.validar_hasta_ayer(hoy_d)
    except Exception:
        logger.error("Error en la validación masiva", exc_info=True)
        return HttpResponse("No se pudo guardar", status=500)
    if not es_htmx(request):
        return redirect(reverse("hoy"))
    return render_page_or_partial(
        request,
        "partials/_respuesta_masiva.html",
        "partials/_respuesta_masiva.html",
        _contexto_lista(hoy_d, oob=True),
    )


@protegido
@require_http_methods(["GET", "POST"])
def obs_entrega(request):
    """GET: modal con la observación del día. POST: la guarda y refresca la lista de Hoy."""
    datos = request.POST if request.method == "POST" else request.GET
    try:
        fecha = date.fromisoformat(datos.get("fecha", ""))
    except ValueError:
        logger.warning("Observación con fecha inválida: %s", datos.get("fecha"))
        return HttpResponseBadRequest("Fecha inválida")

    if request.method == "POST":
        try:
            services.guardar_observacion(fecha, datos.get("observaciones"), services.hoy_lima())
        except services.EntregaNoValida as exc:
            logger.warning("Observación rechazada: %s", exc)
            return HttpResponseBadRequest(str(exc))
        except Exception:
            logger.error("Error al guardar la observación de %s", fecha, exc_info=True)
            return HttpResponse("No se pudo guardar", status=500)
        respuesta = HttpResponse(status=204)
        respuesta["HX-Trigger"] = json.dumps({"cerrarModal": True, "hoyActualizado": True})
        return respuesta

    if not es_htmx(request):
        return redirect(reverse("hoy"))
    actual = Entrega.objects.filter(fecha=fecha).values_list("observaciones", flat=True).first()
    ctx = {
        "iso": fecha.isoformat(),
        "etiqueta": formatear_fecha_con_dia(fecha),
        "observaciones": actual or "",
    }
    return render_page_or_partial(request, "partials/_modal_obs.html", "partials/_modal_obs.html", ctx)
