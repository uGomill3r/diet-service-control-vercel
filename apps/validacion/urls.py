from django.urls import path
from . import views

urlpatterns = [
    path("hoy", views.hoy, name="hoy"),
    path("validacion/marcar", views.marcar_entrega, name="marcar_entrega"),
    path("validacion/obs", views.obs_entrega, name="obs_entrega"),
    path("validacion/hasta_ayer", views.validar_hasta_ayer, name="validar_hasta_ayer"),
]
