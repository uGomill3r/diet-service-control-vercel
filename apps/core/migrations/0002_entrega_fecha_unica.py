"""
Deduplica las filas históricas de 'entregas' y agrega una restricción única sobre 'fecha'.
Política de fusión por fecha duplicada: se conserva la fila más reciente (mayor id), con el
máximo de cada flag de entrega y las observaciones distintas unidas con ' | '.
"""
import logging
from django.db import migrations, models
from django.db.models import Count

logger = logging.getLogger(__name__)


def deduplicar_entregas(apps, schema_editor):
    Entrega = apps.get_model("core", "Entrega")
    fechas = (
        Entrega.objects.values("fecha")
        .annotate(n=Count("id"))
        .filter(n__gt=1)
        .values_list("fecha", flat=True)
    )
    for fecha in list(fechas):
        filas = list(Entrega.objects.filter(fecha=fecha).order_by("id"))
        conservar = filas[-1]
        alm = [f.entregado_almuerzo for f in filas if f.entregado_almuerzo is not None]
        cen = [f.entregado_cena for f in filas if f.entregado_cena is not None]
        obs = []
        for f in filas:
            texto = (f.observaciones or "").strip()
            if texto and texto not in obs:
                obs.append(texto)
        conservar.entregado_almuerzo = max(alm) if alm else None
        conservar.entregado_cena = max(cen) if cen else None
        conservar.observaciones = " | ".join(obs) or None
        conservar.save()
        eliminadas = Entrega.objects.filter(fecha=fecha).exclude(pk=conservar.pk).delete()[0]
        logger.warning("Entregas duplicadas en %s: %d filas fusionadas", fecha, eliminadas)


class Migration(migrations.Migration):

    dependencies = [("core", "0001_initial")]

    operations = [
        migrations.RunPython(deduplicar_entregas, migrations.RunPython.noop),
        migrations.AddConstraint(
            model_name="entrega",
            constraint=models.UniqueConstraint(fields=["fecha"], name="entregas_fecha_unica"),
        ),
    ]
