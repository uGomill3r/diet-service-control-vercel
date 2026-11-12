"""
Vistas de reportes por ciclo de pago.
Migrado desde blueprints/reportes.py de Flask.
"""
import logging
from datetime import datetime
from django.shortcuts import render
from django.db.models import Sum
from apps.core.decorators import protegido
from apps.core.models import Entrega, Pago, CicloPago
from apps.core.utils import formatear_fecha_con_dia

logger = logging.getLogger(__name__)


@protegido
def reporte_ciclo(request):
    """Muestra las entregas dentro de un ciclo de pago seleccionado."""
    tipo = request.GET.get("tipo") or request.POST.get("tipo") or "almuerzo"
    if tipo not in ["almuerzo", "cena"]:
        tipo = "almuerzo"

    logger.info("Cargando reporte de ciclo — tipo: %s", tipo)

    ciclos_qs = CicloPago.objects.filter(tipo=tipo).order_by("-fecha_inicio")
    ciclos = list(ciclos_qs.values_list("id", "fecha_inicio", "fecha_fin"))

    registros = []
    ciclo_seleccionado = None
    ciclo_info = None
    cantidad_pagada = 0

    if request.method == "POST":
        fecha_str = request.POST.get("fecha")
        if fecha_str:
            try:
                fecha_inicio = datetime.strptime(fecha_str, "%Y-%m-%d").date()
            except ValueError:
                fecha_inicio = None

            if fecha_inicio:
                ciclo = ciclos_qs.filter(fecha_inicio=fecha_inicio).first()
                if ciclo:
                    ciclo_seleccionado = ciclo.fecha_inicio
                    ciclo_info = (ciclo.fecha_inicio, ciclo.fecha_fin)
                    logger.debug("Ciclo seleccionado — id: %d, inicio: %s", ciclo.id, ciclo.fecha_inicio)

                    cantidad_pagada = (
                        Pago.objects.filter(tipo=tipo, ciclo=ciclo)
                        .aggregate(total=Sum("cantidad"))["total"] or 0
                    )

                    fecha_fin_real = ciclo.fecha_fin or datetime.now().date()
                    campo_entregado = (
                        "entregado_almuerzo" if tipo == "almuerzo" else "entregado_cena"
                    )
                    filtro_entrega = {campo_entregado: 1}

                    fechas_entregadas = (
                        Entrega.objects.filter(
                            fecha__gte=ciclo.fecha_inicio,
                            fecha__lte=fecha_fin_real,
                            **filtro_entrega,
                        )
                        .order_by("fecha")
                        .values_list("fecha", flat=True)
                    )

                    for i, fecha in enumerate(fechas_entregadas):
                        texto = formatear_fecha_con_dia(fecha)
                        excedido = i >= cantidad_pagada
                        registros.append({"fecha": texto, "excedido": excedido})

                    logger.info(
                        "Reporte generado — %d entregas, %d pagadas, %d excedidas",
                        len(registros), cantidad_pagada,
                        sum(1 for r in registros if r["excedido"]),
                    )

    return render(
        request,
        "reporte_ciclo.html",
        {
            "tipo": tipo,
            "ciclos": ciclos,
            "registros": registros,
            "ciclo_seleccionado": ciclo_seleccionado,
            "ciclo_info": ciclo_info,
            "cantidad_pagada": cantidad_pagada,
        },
    )
