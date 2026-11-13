"""
Lógica de la pantalla Hoy: estado de validación de entregas, contadores y saldos.
"""
import logging
from django.db import transaction
from django.utils import timezone

from apps.core.models import Entrega, Pedido
from apps.core.utils import formatear_fecha_con_dia
# Se reutiliza la fórmula de ciclos del dashboard para que los saldos coincidan
from apps.dashboard.views import _ciclo_vigente, _en_rango, _pagos_ciclo, _rango_ciclo

logger = logging.getLogger(__name__)

TIPOS = ("almuerzo", "cena")


class EntregaNoValida(ValueError):
    """La entrega solicitada no corresponde a un pedido existente."""


def hoy_lima():
    """Fecha actual en America/Lima (Vercel corre en UTC)."""
    return timezone.localdate()


def cargar_estado():
    """Devuelve (pedidos, entregas): lista de filas de pedido y dict fecha -> (alm, cen, obs)."""
    pedidos = list(
        Pedido.objects.values_list(
            "fecha", "almuerzo", "cena", "feriado", "entrada", "fondo", "plato_cena"
        )
    )
    entregas = {
        fecha: (a or 0, c or 0, obs or "")
        for fecha, a, c, obs in Entrega.objects.values_list(
            "fecha", "entregado_almuerzo", "entregado_cena", "observaciones"
        )
    }
    logger.debug("Estado cargado: %d pedidos, %d entregas", len(pedidos), len(entregas))
    return pedidos, entregas


def calcular_contadores(pedidos, entregas, hoy):
    """Pendientes (hasta hoy) y saldo del ciclo vigente, con la misma fórmula del dashboard."""
    ciclo_alm = _ciclo_vigente("almuerzo", hoy)
    ciclo_cen = _ciclo_vigente("cena", hoy)
    alm_ini, alm_fin = _rango_ciclo(ciclo_alm)
    cen_ini, cen_fin = _rango_ciclo(ciclo_cen)

    alm_ent = alm_por = cen_ent = cen_por = pend_alm = pend_cen = 0
    for fecha, a_ped, c_ped, feriado, *_resto in pedidos:
        a_ped, c_ped = a_ped or 0, c_ped or 0
        a_ent, c_ent, _obs = entregas.get(fecha, (0, 0, ""))
        if _en_rango(fecha, alm_ini, alm_fin):
            alm_ent += a_ent
            if a_ped and not a_ent and fecha >= hoy:
                alm_por += 1
        if _en_rango(fecha, cen_ini, cen_fin):
            cen_ent += c_ent
            if c_ped and not c_ent and fecha >= hoy:
                cen_por += 1
        if fecha <= hoy and not feriado:
            pend_alm += 1 if (a_ped and not a_ent) else 0
            pend_cen += 1 if (c_ped and not c_ent) else 0

    contadores = {
        "pend_alm": pend_alm,
        "pend_cen": pend_cen,
        "saldo_alm": _pagos_ciclo("almuerzo", ciclo_alm) - alm_ent - alm_por,
        "saldo_cen": _pagos_ciclo("cena", ciclo_cen) - cen_ent - cen_por,
    }
    logger.info("Contadores Hoy: %s", contadores)
    return contadores


def _construir_dia(fila, entregas, hoy):
    """Arma el dict de una tarjeta; devuelve None si el día no aplica (feriado/sin comidas)."""
    fecha, a_ped, c_ped, feriado, entrada, fondo, plato_cena = fila
    if feriado or not (a_ped or c_ped):
        return None
    a_ent, c_ent, obs = entregas.get(fecha, (0, 0, ""))
    return {
        "iso": fecha.isoformat(),
        "etiqueta": formatear_fecha_con_dia(fecha),
        "es_hoy": fecha == hoy,
        "observaciones": obs,
        "almuerzo": {
            "aplica": bool(a_ped),
            "entregado": bool(a_ent),
            "entrada": entrada or "",
            "fondo": fondo or "",
        },
        "cena": {
            "aplica": bool(c_ped),
            "entregado": bool(c_ent),
            "plato": plato_cena or "",
        },
    }


def armar_dias(pedidos, entregas, hoy):
    """Devuelve (dia_hoy, pendientes, validados) para la pantalla Hoy."""
    dia_hoy, pendientes, validados = None, [], []
    for fila in sorted((p for p in pedidos if p[0] <= hoy), key=lambda p: p[0], reverse=True):
        dia = _construir_dia(fila, entregas, hoy)
        if dia is None:
            continue
        if dia["es_hoy"]:
            dia_hoy = dia
            continue
        incompleto = any(dia[t]["aplica"] and not dia[t]["entregado"] for t in TIPOS)
        (pendientes if incompleto else validados).append(dia)
    return dia_hoy, pendientes, validados[:3]


def guardar_entrega(fecha, tipo, valor, hoy):
    """Fija explícitamente (1/0) la entrega de un tipo en una fecha. Idempotente."""
    if tipo not in TIPOS:
        raise EntregaNoValida(f"Tipo inválido: {tipo}")
    if fecha > hoy:
        raise EntregaNoValida(f"No se puede validar una fecha futura: {fecha}")
    pedido = Pedido.objects.filter(fecha=fecha, feriado=False).first()
    if pedido is None or not getattr(pedido, tipo):
        raise EntregaNoValida(f"No hay pedido de {tipo} el {fecha}")
    Entrega.objects.update_or_create(fecha=fecha, defaults={f"entregado_{tipo}": valor})
    logger.info("Entrega %s %s = %d", tipo, fecha, valor)


def guardar_observacion(fecha, texto, hoy):
    """Guarda (o borra, si va vacía) la observación de entrega de un día con pedido."""
    if fecha > hoy:
        raise EntregaNoValida(f"No se puede anotar una fecha futura: {fecha}")
    if not Pedido.objects.filter(fecha=fecha).exists():
        raise EntregaNoValida(f"No hay pedido el {fecha}")
    texto = (texto or "").strip()
    Entrega.objects.update_or_create(fecha=fecha, defaults={"observaciones": texto or None})
    logger.info("Observación de entrega %s %s", fecha, "guardada" if texto else "borrada")


def validar_hasta_ayer(hoy):
    """Marca como entregado todo pedido anterior a hoy, salvo días con observaciones."""
    pedidos = Pedido.objects.filter(fecha__lt=hoy, feriado=False)
    existentes = {e.fecha: e for e in Entrega.objects.filter(fecha__lt=hoy)}
    crear, actualizar, omitidos = [], [], 0
    for p in pedidos:
        ent = existentes.get(p.fecha)
        if ent and (ent.observaciones or "").strip():
            omitidos += 1
            continue
        marca_alm = bool(p.almuerzo) and not (ent and ent.entregado_almuerzo)
        marca_cen = bool(p.cena) and not (ent and ent.entregado_cena)
        if not (marca_alm or marca_cen):
            continue
        if ent is None:
            crear.append(
                Entrega(
                    fecha=p.fecha,
                    entregado_almuerzo=1 if marca_alm else 0,
                    entregado_cena=1 if marca_cen else 0,
                )
            )
        else:
            if marca_alm:
                ent.entregado_almuerzo = 1
            if marca_cen:
                ent.entregado_cena = 1
            actualizar.append(ent)
    with transaction.atomic():
        Entrega.objects.bulk_create(crear)
        Entrega.objects.bulk_update(actualizar, ["entregado_almuerzo", "entregado_cena"])
    total = len(crear) + len(actualizar)
    logger.info("Validación masiva: %d días marcados, %d omitidos por observaciones", total, omitidos)
    return total
