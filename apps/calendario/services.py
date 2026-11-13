"""
Datos del calendario unificado (semana/mes) y del modal de edición de un día.
"""
import calendar
import logging
from datetime import date, timedelta

from apps.core.models import CicloPago, Entrega, Pedido
from apps.core.utils import estado_textual

logger = logging.getLogger(__name__)

CABECERA = ["Lun", "Mar", "Mié", "Jue", "Vie"]
MESES_ES = [
    "", "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _color(pedido, entregado, fecha, hoy):
    """light = sin pedido, success = entregado, danger = pasado sin entregar, warning = pendiente."""
    if not pedido:
        return "light"
    if entregado:
        return "success"
    return "danger" if fecha < hoy else "warning"


def _cargar(inicio, fin):
    """Pedidos, entregas e inicios de ciclo del rango [inicio, fin]."""
    pedidos = {
        f: (a or 0, c or 0, bool(fer))
        for f, a, c, fer in Pedido.objects.filter(fecha__range=(inicio, fin)).values_list(
            "fecha", "almuerzo", "cena", "feriado"
        )
    }
    entregas = {
        f: (a or 0, c or 0)
        for f, a, c in Entrega.objects.filter(fecha__range=(inicio, fin)).values_list(
            "fecha", "entregado_almuerzo", "entregado_cena"
        )
    }
    ciclos = {}
    for f, tipo in CicloPago.objects.filter(fecha_inicio__range=(inicio, fin)).values_list(
        "fecha_inicio", "tipo"
    ):
        ciclos.setdefault(f, set()).add(tipo)
    return pedidos, entregas, ciclos


def _dia(fecha, datos, hoy):
    pedidos, entregas, ciclos = datos
    a_ped, c_ped, feriado = pedidos.get(fecha, (0, 0, False))
    a_ent, c_ent = entregas.get(fecha, (0, 0))
    return {
        "iso": fecha.isoformat(),
        "numero": fecha.day,
        "nombre": CABECERA[fecha.weekday()],
        "fecha_corta": fecha.strftime("%d/%m"),
        "es_hoy": fecha == hoy,
        "feriado": feriado,
        "estado": {
            "almuerzo": _color(a_ped, a_ent, fecha, hoy),
            "cena": _color(c_ped, c_ent, fecha, hoy),
        },
        "texto": estado_textual(fecha, (a_ped, c_ped), (a_ent, c_ent), feriado),
        "ciclo_inicio": bool(ciclos.get(fecha)),
    }


def construir_semana(ancla, hoy):
    """Semana lun-vie que contiene `ancla`."""
    lunes = ancla - timedelta(days=ancla.weekday())
    viernes = lunes + timedelta(days=4)
    datos = _cargar(lunes, viernes)
    dias = [_dia(lunes + timedelta(days=i), datos, hoy) for i in range(5)]
    logger.info("Calendario semanal %s: %d días", lunes, len(dias))
    return {
        "titulo": f"Semana {lunes.isocalendar().week} · {lunes:%d/%m} – {viernes:%d/%m}",
        "dias": dias,
        "ancla": lunes.isoformat(),
        "anterior": (lunes - timedelta(days=7)).isoformat(),
        "siguiente": (lunes + timedelta(days=7)).isoformat(),
    }


def construir_mes(ancla, hoy):
    """Grilla mensual lun-vie del mes de `ancla`."""
    primero = ancla.replace(day=1)
    ultimo = date(ancla.year, ancla.month, calendar.monthrange(ancla.year, ancla.month)[1])
    datos = _cargar(primero, ultimo)
    semanas = []
    for fila in calendar.monthcalendar(ancla.year, ancla.month):
        habiles = fila[:5]
        if not any(habiles):
            continue
        semanas.append(
            [_dia(date(ancla.year, ancla.month, n), datos, hoy) if n else None for n in habiles]
        )
    logger.info("Calendario mensual %s: %d semanas", primero, len(semanas))
    return {
        "titulo": f"{MESES_ES[ancla.month].capitalize()} {ancla.year}",
        "semanas": semanas,
        "cabecera": CABECERA,
        "ancla": primero.isoformat(),
        "anterior": (primero - timedelta(days=1)).replace(day=1).isoformat(),
        "siguiente": (primero + timedelta(days=32)).replace(day=1).isoformat(),
    }


def datos_modal(fecha):
    """Contexto del modal de edición del pedido de un día."""
    pedido = Pedido.objects.filter(fecha=fecha).first()
    entrega = Entrega.objects.filter(fecha=fecha).first()
    dias = ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"]
    return {
        "iso": fecha.isoformat(),
        "fecha_ddmmaaaa": fecha.strftime("%d-%m-%Y"),
        "etiqueta": f"{dias[fecha.weekday()]} {fecha.strftime('%d-%m-%Y')}",
        "almuerzo": bool(pedido and pedido.almuerzo),
        "cena": bool(pedido and pedido.cena),
        "feriado": bool(pedido and pedido.feriado),
        "entrada": (pedido.entrada if pedido else "") or "",
        "fondo": (pedido.fondo if pedido else "") or "",
        "plato_cena": (pedido.plato_cena if pedido else "") or "",
        "obs_pedido": (pedido.observaciones if pedido else "") or "",
        "ent_almuerzo": bool(entrega and entrega.entregado_almuerzo),
        "ent_cena": bool(entrega and entrega.entregado_cena),
    }


def guardar_pedido(fecha, datos):
    """Guarda el pedido de un día (no toca la entrega: eso se valida en Hoy)."""
    pedido, creado = Pedido.objects.update_or_create(
        fecha=fecha,
        defaults={
            "semana": fecha.isocalendar().week,
            "almuerzo": 1 if datos.get("almuerzo") == "on" else 0,
            "cena": 1 if datos.get("cena") == "on" else 0,
            "feriado": datos.get("feriado") == "on",
            "entrada": (datos.get("entrada") or "").strip(),
            "fondo": (datos.get("fondo") or "").strip(),
            "plato_cena": (datos.get("plato_cena") or "").strip(),
            "observaciones": (datos.get("obs_pedido") or "").strip(),
        },
    )
    logger.info("Pedido %s guardado (creado=%s)", fecha, creado)
    return pedido
