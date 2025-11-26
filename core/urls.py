from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import EmpresaViewSet, EntrevistaView, FavoritosView, UserViewSet, UsuarioViewSet, postular_vacante, listar_empresas, actualizar_estado_postulacion,contactar_candidato


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
    path( 'api/auth/password-reset-confirm/<str:uidb64>/<str:token>/',views.PasswordResetConfirmView.as_view(),name='api_password_reset_confirm', ),

    path("api/perfil_adicional/", views.PerfilUsuarioView.as_view()),

    path('vacantes/crear/', views.crear_vacante, name='crear_vacante'),
    path('vacantes/<int:vacante_id>/editar/', views.actualizar_vacante, name='actualizar_vacante'),
    path('vacantes/<int:vacante_id>/eliminar/', views.eliminar_vacante, name='eliminar_vacante'),
    path('vacantes/<int:vacante_id>/publicar/', views.publicar_vacante, name='publicar_vacante'),
    path('vacantes/', views.listar_vacantes, name='listar_vacantes'),
    path("vacantes/<int:vacante_id>/postular/", views.postular_vacante, name="postular_vacante"),
    path('empresas/', views.listar_empresas, name='listar_empresas'),
    path('vacantes/<int:vacante_id>/asignar_rrhh/', views.asignar_rrhh_a_vacante, name='asignar_rrhh_a_vacante'),
    path('vacantes/mis_asignadas/', views.mis_vacantes_asignadas, name='mis_vacantes_asignadas'),
    path('vacantes/<int:vacante_id>/', views.obtener_vacante, name='obtener_vacante'),


    path('api/asignar-empleado/', views.AsignarEmpleadoView.as_view(), name='asignar-empleado'),
    path("api/empresa/<int:empresa_id>/trabajadores/", views.listar_trabajadores, name="listar_trabajadores"),

    path("api/favoritos/", FavoritosView.as_view()), # GET (Ver favoritos del usuario logueado) y POST (Marcar nuevo favorito)
    path("api/favoritos/<int:candidato_id>/", FavoritosView.as_view()),
    path("vacantes/<int:id_vacante>/postulaciones/", views.listar_postulaciones_por_vacante, name="listar_postulaciones_por_vacante"), # GET (Ver postulaciones del usuario logueado)
    path('reclutador/postulaciones/<int:postulacion_id>/estado/', actualizar_estado_postulacion),
    path('reclutador/postulaciones/<int:postulacion_id>/contactar/', contactar_candidato),
    
    # Crear entrevista
    path("api/entrevistas/", EntrevistaView.as_view(), name="crear_entrevista"),
    # Listar entrevistas por postulacion
    path("api/entrevistas/postulacion/<int:postulacion_id>/", EntrevistaView.as_view(),
         name="listar_entrevistas"),
    # Obtener, actualizar o eliminar una entrevista
    path("api/entrevistas/<int:entrevista_id>/", EntrevistaView.as_view(),
         name="entrevista_detalle"),


]

