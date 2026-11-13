from django.urls import path
from django.views.generic import RedirectView
from . import views

urlpatterns = [
    path("calendario", views.calendario, name="calendario"),
    # Rutas antiguas: se conservan los nombres y se redirige al calendario unificado
    path("semana", RedirectView.as_view(url="/calendario?vista=semana"), name="semana"),
    path("mes", RedirectView.as_view(url="/calendario?vista=mes"), name="mes"),
    path("calendario/dia", views.modal_dia, name="modal_dia"),
    path("calendario/dia/guardar", views.guardar_dia, name="guardar_dia"),
]
