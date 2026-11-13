"""
Vistas para importar el plan de almuerzos desde el .eml de confirmación
de pedido de menú enviado por dietservice.pe.

Flujo (todo en la misma página con HTMX; sin JS funciona como páginas completas):
1. GET  /importar            → formulario de subida del .eml
2. POST /importar            → parsea el .eml y muestra la previsualización
3. POST /importar/confirmar  → guarda los pedidos y muestra el resultado
"""
import json
import logging
from datetime import datetime

from django.shortcuts import redirect
from django.urls import reverse

from apps.core.decorators import protegido
from apps.core.htmx import render_page_or_partial
from apps.core.models import Pedido
from .parser import parsear_eml

logger = logging.getLogger(__name__)


def _formulario(request, error=None):
    """Formulario de subida, con un mensaje de error opcional."""
    return render_page_or_partial(request, "importar.html", "partials/_importar_form.html", {"error": error})


@protegido
def importar_eml(request):
    """GET: formulario de subida. POST: parsea el .eml y muestra la previsualización."""
    if request.method != "POST":
        return _formulario(request)

    archivo = request.FILES.get("archivo_eml")
    if not archivo:
        return _formulario(request, "Debes seleccionar un archivo .eml.")
    if not archivo.name.lower().endswith(".eml"):
        return _formulario(request, "El archivo debe tener extensión .eml.")

    logger.info("Archivo .eml recibido: %s (%d bytes)", archivo.name, archivo.size)
    try:
        resultado = parsear_eml(archivo.read())
    except Exception:
        logger.error("Error al parsear el .eml %s", archivo.name, exc_info=True)
        return _formulario(request, "No se pudo leer el archivo. Verifica que sea un .eml válido.")

    if not resultado["dias"]:
        logger.warning("El .eml %s no contiene días", archivo.name)
        return _formulario(
            request,
            "No se pudieron extraer días del archivo. "
            "Verifica que sea el correo de confirmación de pedido de menú.",
        )

    # Marcar qué fechas ya tienen pedido para advertir que se sobreescribirán
    fechas_validas = [d["fecha"] for d in resultado["dias"] if d["fecha"]]
    existentes = set(Pedido.objects.filter(fecha__in=fechas_validas).values_list("fecha", flat=True))
    logger.info("Fechas con pedido existente: %d de %d", len(existentes), len(fechas_validas))
    for dia in resultado["dias"]:
        dia["ya_existe"] = bool(dia["fecha"]) and dia["fecha"] in existentes

    # Solo se serializa lo necesario para la confirmación
    datos_confirmacion = [
        {
            "fecha": d["fecha"].isoformat(),
            "entrada": d["entrada"],
            "fondo": d["fondo"],
            "cena": d["cena"],
        }
        for d in resultado["dias"]
        if d["fecha"] and (d["entrada"] or d["fondo"] or d["cena"])
    ]
    return render_page_or_partial(
        request,
        "importar_preview.html",
        "partials/_importar_preview.html",
        {
            "resultado": resultado,
            "datos_json": json.dumps(datos_confirmacion),
            "total_dias": len(resultado["dias"]),
            "con_errores": len(resultado["errores"]),
        },
    )


@protegido
def confirmar_importacion(request):
    """POST: guarda los días confirmados (update_or_create por fecha) y muestra el resultado."""
    if request.method != "POST":
        return redirect(reverse("importar"))

    try:
        dias = json.loads(request.POST.get("datos_json", "[]"))
        if not isinstance(dias, list):
            raise ValueError("Se esperaba una lista de días")
    except (json.JSONDecodeError, ValueError):
        logger.error("JSON de confirmación inválido", exc_info=True)
        return _formulario(request, "Error al procesar los datos. Intenta nuevamente.")

    logger.info("Confirmando importación de %d días", len(dias))
    guardados = errores = 0

    for dia in dias:
        fecha_str = dia.get("fecha")
        if not fecha_str:
            continue
        try:
            fecha = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except ValueError:
            logger.error("Fecha inválida en confirmación: %s", fecha_str)
            errores += 1
            continue

        entrada = dia.get("entrada") or ""
        fondo = dia.get("fondo") or ""
        plato_cena = dia.get("cena") or ""
        try:
            defaults = {
                "semana": fecha.isocalendar().week,
                "almuerzo": 1,  # se marca como pedido de almuerzo
                "entrada": entrada,
                "fondo": fondo,
            }
            if plato_cena:
                defaults["cena"] = 1  # se marca como pedido de cena
                defaults["plato_cena"] = plato_cena
            _, creado = Pedido.objects.update_or_create(fecha=fecha, defaults=defaults)
            logger.debug(
                "Pedido %s para %s — entrada: %s, fondo: %s, cena: %s",
                "creado" if creado else "actualizado", fecha, entrada, fondo, plato_cena or "-",
            )
            guardados += 1
        except Exception:
            logger.error("Error guardando pedido para %s", fecha_str, exc_info=True)
            errores += 1

    logger.info("Importación finalizada — guardados: %d, errores: %d", guardados, errores)
    return render_page_or_partial(
        request,
        "importar_resultado.html",
        "partials/_importar_resultado.html",
        {"guardados": guardados, "errores": errores},
    )
