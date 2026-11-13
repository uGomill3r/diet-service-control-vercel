"""
Vistas de reportes por ciclo de pago (selectores por HTMX, vía GET).
"""
import logging
from datetime import date

from django.db.models import Sum
from django.utils import timezone
from django.views.decorators.http import require_GET

from apps.core.decorators import protegido
from apps.core.htmx import render_page_or_partial
from apps.core.models import CicloPago, Entrega, Pago
from apps.core.utils import formatear_fecha_con_dia

logger = logging.getLogger(__name__)


@protegido
@require_GET
def reporte_ciclo(request):
    """Entregas dentro del ciclo seleccionado (tipo y fecha de inicio por query string)."""
    tipo = request.GET.get("tipo", "almuerzo")
    if tipo not in ("almuerzo", "cena"):
        tipo = "almuerzo"
    logger.info("Cargando reporte de ciclo — tipo: %s", tipo)

    ciclos_qs = CicloPago.objects.filter(tipo=tipo).order_by("-fecha_inicio")
    ciclos = list(ciclos_qs.values_list("id", "fecha_inicio", "fecha_fin"))

    registros, ciclo_seleccionado, ciclo_info, cantidad_pagada = [], None, None, 0

    try:
        fecha_inicio = date.fromisoformat(request.GET.get("fecha", ""))
    except ValueError:
        fecha_inicio = None

    ciclo = ciclos_qs.filter(fecha_inicio=fecha_inicio).first() if fecha_inicio else None
    if ciclo:
        ciclo_seleccionado = ciclo.fecha_inicio
        ciclo_info = (ciclo.fecha_inicio, ciclo.fecha_fin)
        logger.debug("Ciclo seleccionado — id: %d, inicio: %s", ciclo.id, ciclo.fecha_inicio)

        cantidad_pagada = (
            Pago.objects.filter(tipo=tipo, ciclo=ciclo).aggregate(total=Sum("cantidad"))["total"] or 0
        )
        fecha_fin_real = ciclo.fecha_fin or timezone.localdate()
        fechas = (
            Entrega.objects.filter(
                fecha__gte=ciclo.fecha_inicio,
                fecha__lte=fecha_fin_real,
                **{f"entregado_{tipo}": 1},
            )
            .order_by("fecha")
            .values_list("fecha", flat=True)
        )
        for i, fecha in enumerate(fechas):
            registros.append({"fecha": formatear_fecha_con_dia(fecha), "excedido": i >= cantidad_pagada})
        logger.info(
            "Reporte generado — %d entregas, %d pagadas, %d excedidas",
            len(registros), cantidad_pagada, sum(1 for r in registros if r["excedido"]),
        )

    return render_page_or_partial(
        request,
        "reporte_ciclo.html",
        "partials/_reporte.html",
        {
            "tipo": tipo,
            "ciclos": ciclos,
            "registros": registros,
            "ciclo_seleccionado": ciclo_seleccionado,
            "ciclo_info": ciclo_info,
            "cantidad_pagada": cantidad_pagada,
        },
    )
