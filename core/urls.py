# core/urls.py
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from core.views import EmpresaViewSet, UserViewSet, UsuarioViewSet, home

router = DefaultRouter()
router.register(r"empresas", EmpresaViewSet, basename="empresa")
router.register(r"usuarios", UserViewSet, basename="usuario")
router.register(r"usuarios_supabase", UsuarioViewSet, basename="usuario_supabase")

urlpatterns = [
    path('', home, name='home'),
    path('api/', include(router.urls)),
]
