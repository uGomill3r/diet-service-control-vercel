"""
Vistas de registro y edición de pagos y ciclos de pago (con HTMX).
Las altas y ediciones responden con el parcial de listas; sin HTMX conservan
el flujo clásico (redirección a /pagos).
"""
import logging
from datetime import date

from django.contrib import messages
from django.db import transaction
from django.db.models import Sum
from django.http import HttpResponse, HttpResponseBadRequest
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.core.decorators import protegido
from apps.core.htmx import es_htmx, render_page_or_partial
from apps.core.models import CicloPago, Log, Pago, Pedido
from apps.core.utils import ciclo_agotado, formatear_fecha

logger = logging.getLogger(__name__)

TIPOS = ("almuerzo", "cena")


class DatosInvalidos(ValueError):
    """Datos de formulario inválidos (se informan al usuario con un 400)."""


def _leer_pago(post):
    """Valida y convierte los campos del formulario de pago."""
    try:
        fecha = date.fromisoformat(post.get("fecha", ""))
        monto = float(post.get("monto", ""))
        cantidad = int(post.get("cantidad", ""))
    except ValueError:
        raise DatosInvalidos("Revise la fecha, el monto y la cantidad.")
    tipo = post.get("tipo", "")
    if tipo not in TIPOS:
        raise DatosInvalidos("Tipo de comida inválido.")
    if cantidad < 1 or monto < 0:
        raise DatosInvalidos("La cantidad debe ser al menos 1 y el monto no puede ser negativo.")
    return fecha, tipo, monto, cantidad


def _leer_fechas_ciclo(post):
    """Valida inicio (obligatorio) y fin (opcional) de un ciclo."""
    try:
        inicio = date.fromisoformat(post.get("fecha_inicio", ""))
        fin = date.fromisoformat(post["fecha_fin"]) if post.get("fecha_fin") else None
    except ValueError:
        raise DatosInvalidos("Revise las fechas del ciclo.")
    if fin and fin < inicio:
        raise DatosInvalidos("La fecha de fin no puede ser anterior a la fecha de inicio.")
    return inicio, fin


def _contexto_listas(aviso=None):
    """Contexto de las listas de pagos, totales y ciclos."""
    pagos = [
        {
            "id": p.id,
            "fecha": formatear_fecha(p.fecha),
            "tipo": p.tipo,
            "cantidad": p.cantidad,
            "monto": p.monto,
            "ciclo": formatear_fecha(p.ciclo.fecha_inicio) if p.ciclo else None,
        }
        for p in Pago.objects.select_related("ciclo").order_by("-fecha", "-id")
    ]
    totales = {
        row["tipo"]: row["total"]
        for row in Pago.objects.values("tipo").annotate(total=Sum("monto"))
    }
    ciclos = [
        {
            "id": c.id,
            "tipo": c.tipo,
            "inicio": formatear_fecha(c.fecha_inicio),
            "fin": formatear_fecha(c.fecha_fin) if c.fecha_fin else None,
        }
        for c in CicloPago.objects.order_by("-fecha_inicio")
    ]
    logger.debug("Listando %d pagos y %d ciclos", len(pagos), len(ciclos))
    return {"pagos": pagos, "totales": totales, "ciclos": ciclos, "aviso": aviso}


def _respuesta_listas(request, aviso=None):
    return render_page_or_partial(
        request, "pagos.html", "partials/_pagos_listas.html", _contexto_listas(aviso)
    )


@transaction.atomic
def _registrar_pago(fecha, tipo, monto, cantidad):
    """Registra el pago y abre/cierra ciclos según corresponda. Devuelve un aviso o None."""
    ciclo_activo = (
        CicloPago.objects.filter(tipo=tipo, fecha_fin__isnull=True).order_by("-fecha_inicio").first()
    )
    ciclo, aviso = None, None

    if ciclo_activo is None:
        ciclo = CicloPago.objects.create(tipo=tipo, fecha_inicio=fecha)
        logger.info("Sin ciclo activo para '%s' — nuevo ciclo creado id=%d", tipo, ciclo.id)
    elif ciclo_agotado(ciclo_activo):
        ultimo_pedido = (
            Pedido.objects.filter(
                **{f"{tipo}__gt": 0}, fecha__gte=ciclo_activo.fecha_inicio, fecha__lt=fecha
            )
            .order_by("-fecha")
            .values_list("fecha", flat=True)
            .first()
        )
        ciclo_activo.fecha_fin = ultimo_pedido or fecha
        ciclo_activo.save()
        logger.info("Ciclo id=%d agotado — cerrado con fecha_fin: %s", ciclo_activo.id, ciclo_activo.fecha_fin)
        ciclo = CicloPago.objects.create(tipo=tipo, fecha_inicio=fecha)
        logger.info("Nuevo ciclo creado id=%d", ciclo.id)
    else:
        aviso = (
            f"El paquete de {tipo} actual todavía no se agotó. "
            "El pago fue registrado sin ciclo asignado (pendiente)."
        )
        logger.warning("Pago registrado sin ciclo — ciclo activo id=%d aún no agotado", ciclo_activo.id)

    pago = Pago.objects.create(fecha=fecha, tipo=tipo, monto=monto, cantidad=cantidad, ciclo=ciclo)
    Log.objects.create(
        timestamp=timezone.now(),
        accion="Pago registrado",
        detalle=f"{fecha} | {tipo} x {monto} (ciclo {ciclo.id if ciclo else 'pendiente'})",
    )
    logger.info("Pago registrado — id: %d, ciclo: %s", pago.id, ciclo.id if ciclo else "pendiente")
    return aviso


@protegido
def pagos(request):
    """Lista de pagos y formulario para registrar uno nuevo."""
    if request.method == "POST":
        try:
            fecha, tipo, monto, cantidad = _leer_pago(request.POST)
        except DatosInvalidos as exc:
            logger.warning("Pago rechazado: %s", exc)
            return HttpResponseBadRequest(str(exc))
        try:
            aviso = _registrar_pago(fecha, tipo, monto, cantidad)
        except Exception:
            logger.error("Error al registrar el pago", exc_info=True)
            return HttpResponse("No se pudo guardar", status=500)
        if es_htmx(request):
            return _respuesta_listas(request, aviso)
        if aviso:
            request.session["aviso_pagos"] = aviso
        return redirect(reverse("pagos"))

    aviso = None if es_htmx(request) else request.session.pop("aviso_pagos", None)
    return _respuesta_listas(request, aviso)


@protegido
def editar_pago(request, id):
    """Edición de un pago: fila inline con HTMX o formulario completo como respaldo."""
    pago_obj = get_object_or_404(Pago, id=id)

    if request.method == "POST":
        try:
            fecha, tipo, monto, cantidad = _leer_pago(request.POST)
            ciclo = None
            ciclo_id = request.POST.get("ciclo_id") or None
            if ciclo_id:
                ciclo = CicloPago.objects.filter(id=int(ciclo_id)).first()
                if ciclo is None:
                    raise DatosInvalidos("El ciclo seleccionado no existe.")
        except (DatosInvalidos, ValueError) as exc:
            logger.warning("Edición de pago id=%d rechazada: %s", id, exc)
            return HttpResponseBadRequest(str(exc))

        if ciclo is None and pago_obj.ciclo_id:
            logger.warning("Pago id=%d quedará sin ciclo asociado (antes: ciclo id=%d)", id, pago_obj.ciclo_id)
        logger.info("Editando pago id=%d — de %s/%s a %s/%s", id, pago_obj.fecha, pago_obj.tipo, fecha, tipo)
        try:
            pago_obj.fecha, pago_obj.tipo = fecha, tipo
            pago_obj.monto, pago_obj.cantidad, pago_obj.ciclo = monto, cantidad, ciclo
            pago_obj.save()
            Log.objects.create(
                timestamp=timezone.now(),
                accion="Pago editado",
                detalle=f"Editado pago {id}: {fecha} | {tipo} x {monto} (ciclo {ciclo.id if ciclo else 'pendiente'})",
            )
        except Exception:
            logger.error("Error al editar el pago id=%d", id, exc_info=True)
            return HttpResponse("No se pudo guardar", status=500)
        logger.info("Pago id=%d actualizado correctamente", id)
        return _respuesta_listas(request) if es_htmx(request) else redirect(reverse("pagos"))

    ciclos = [
        (c.id, f"{c.tipo.capitalize()} desde {formatear_fecha(c.fecha_inicio)}")
        for c in CicloPago.objects.order_by("-fecha_inicio")
    ]
    pago_data = (pago_obj.fecha, pago_obj.tipo, pago_obj.monto, pago_obj.cantidad, pago_obj.ciclo_id)
    return render_page_or_partial(
        request,
        "editar_pago.html",
        "partials/_pago_fila_edicion.html",
        {"pago": pago_data, "pago_id": id, "ciclos": ciclos},
    )


@protegido
def editar_ciclo(request, id):
    """
    Corrige manualmente las fechas de inicio/fin de un ciclo de pago.

    Necesario cuando un pago se registró con fecha incorrecta y generó (o cerró)
    un ciclo con un límite equivocado: las fechas del ciclo son independientes
    de la fecha del pago que lo originó.
    """
    ciclo_obj = get_object_or_404(CicloPago, id=id)
    contexto = {"ciclo": ciclo_obj, "ciclo_id": id}

    if request.method == "POST":
        try:
            inicio, fin = _leer_fechas_ciclo(request.POST)
        except DatosInvalidos as exc:
            logger.error("Edición de ciclo id=%d rechazada: %s", id, exc)
            if es_htmx(request):
                return HttpResponseBadRequest(str(exc))
            messages.error(request, str(exc))
            return render(request, "editar_ciclo.html", contexto)

        anterior_inicio, anterior_fin = ciclo_obj.fecha_inicio, ciclo_obj.fecha_fin
        logger.info(
            "Editando ciclo id=%d (%s) — inicio %s -> %s, fin %s -> %s",
            id, ciclo_obj.tipo, anterior_inicio, inicio, anterior_fin, fin,
        )
        try:
            ciclo_obj.fecha_inicio, ciclo_obj.fecha_fin = inicio, fin
            ciclo_obj.save()
            Log.objects.create(
                timestamp=timezone.now(),
                accion="Ciclo de pago editado",
                detalle=(
                    f"Ciclo {id} ({ciclo_obj.tipo}): inicio {anterior_inicio} -> {inicio}, "
                    f"fin {anterior_fin or '—'} -> {fin or '—'}"
                ),
            )
        except Exception:
            logger.error("Error al editar el ciclo id=%d", id, exc_info=True)
            return HttpResponse("No se pudo guardar", status=500)
        logger.info("Ciclo id=%d actualizado correctamente", id)
        return _respuesta_listas(request) if es_htmx(request) else redirect(reverse("pagos"))

    return render_page_or_partial(request, "editar_ciclo.html", "partials/_ciclo_fila_edicion.html", contexto)
