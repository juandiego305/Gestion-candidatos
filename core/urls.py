from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EmpresaViewSet, UserViewSet, UsuarioViewSet

router = DefaultRouter()
router.register(r"empresas", EmpresaViewSet, basename="empresa")
router.register(r"users", UserViewSet, basename="user")
router.register(r"usuarios", UsuarioViewSet, basename="usuario")

from django.urls import path
from core import views

urlpatterns = [
    path('', views.home, name='home'),
    path('api/', include(router.urls)),
    path('api/auth/register/', views.RegisterView.as_view(), name='api_register'),
    path('api/auth/password-reset/', views.PasswordResetRequestView.as_view(), name='api_password_reset'),
    path('api/auth/password-reset-confirm/', views.PasswordResetConfirmView.as_view(), name='api_password_reset_confirm'),
    path('api/token/', views.CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path("api/perfil/", views.PerfilView.as_view(), name="perfil"),

]
