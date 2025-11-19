from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EmpresaViewSet, UserViewSet, UsuarioViewSet, postular_vacante, listar_empresas,listar_usuarios


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
    path('vacantes/crear/', views.crear_vacante, name='crear_vacante'),
    path('vacantes/<int:vacante_id>/editar/', views.actualizar_vacante, name='actualizar_vacante'),
    path('vacantes/<int:vacante_id>/eliminar/', views.eliminar_vacante, name='eliminar_vacante'),
    path('vacantes/<int:vacante_id>/publicar/', views.publicar_vacante, name='publicar_vacante'),
    path('vacantes/', views.listar_vacantes, name='listar_vacantes'),
     path('vacantes/<int:vacante_id>/postular/', views.postular_vacante, name='postular_vacante'),
    path('empresas/', listar_empresas, name='listar_empresas'),
    path("api/perfil_adicional/", views.PerfilUsuarioView.as_view()),
    path("usuarios/", listar_usuarios, name="listar_usuarios"),

]
