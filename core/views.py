from django.http import HttpResponse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.views import APIView
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.conf import settings

class PasswordResetRequestView(APIView):
    """
    Solicita recuperación de contraseña por email o username.
    Envía correo con enlace seguro para restablecer.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        identifier = request.data.get("email") or request.data.get("username")
        if not identifier:
            return Response({"detail": "Debes enviar email o username."}, status=400)

        UserModel = get_user_model()
        user = UserModel.objects.filter(email=identifier).first() or UserModel.objects.filter(username=identifier).first()
        if not user:
            return Response({"detail": "Usuario no encontrado."}, status=404)

        # Generar token y uid
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        token = default_token_generator.make_token(user)
        # Construir enlace (ajusta dominio según tu entorno)
        reset_url = f"http://127.0.0.1:8000/api/auth/password-reset-confirm/?uid={uid}&token={token}"

        # Enviar correo
        send_mail(
            subject="Recuperación de contraseña",
            message=f"Hola {user.username},\n\nPara restablecer tu contraseña haz clic en el siguiente enlace:\n{reset_url}\n\nSi no solicitaste esto, ignora este mensaje.",
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@example.com"),
            recipient_list=[user.email],
            fail_silently=True,
        )

        return Response({"detail": "Correo de recuperación enviado si el usuario existe."}, status=200)


class PasswordResetConfirmView(APIView):
    """
    Restablece la contraseña usando el token recibido por email.
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        uid = request.data.get("uid")
        token = request.data.get("token")
        new_password = request.data.get("new_password")
        if not (uid and token and new_password):
            return Response({"detail": "Faltan datos."}, status=400)

        try:
            uid_int = force_str(urlsafe_base64_decode(uid))
            UserModel = get_user_model()
            user = UserModel.objects.get(pk=uid_int)
        except Exception:
            return Response({"detail": "Usuario inválido."}, status=400)

        if not default_token_generator.check_token(user, token):
            return Response({"detail": "Token inválido o expirado."}, status=400)

        user.set_password(new_password)
        user.save()
        return Response({"detail": "Contraseña restablecida correctamente."}, status=200)
# core/views.py
from django.http import HttpResponse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import User
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.views import APIView
from .serializers_user import UserSerializer
from .models import Empresa
from .serializers import (
    EmpresaSerializer,
    UsuarioSerializer,
    _storage_key_from_public_url,
    supabase,
)
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView

User = get_user_model()


class IsOwner(permissions.BasePermission):
    """
    Permite acceso solo al propietario de la empresa.
    """
    def has_object_permission(self, request, view, obj):
        return obj.owner_id == request.user.id


class EmpresaViewSet(viewsets.ModelViewSet):
    serializer_class = EmpresaSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get_queryset(self):
        return Empresa.objects.filter(owner=self.request.user)

    def perform_destroy(self, instance):
        key = _storage_key_from_public_url(instance.logo_url or "")
        if key:
            try:
                supabase.storage.from_("logos").remove([key])
            except Exception:
                pass
        instance.delete()


class IsAdmin(permissions.BasePermission):
    """Solo administradores pueden gestionar usuarios"""
    def has_permission(self, request, view):
        return request.user and request.user.is_staff

class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("-id")
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]


# ----------------------------
# Usuarios (HU-002)
# ----------------------------
class IsAdminUserOrReadSelf(permissions.BasePermission):
    """
    Permiso compuesto:
    - Si el usuario es staff o superuser => puede listar/crear/editar/destroy (admin).
    - Si no es admin => solo puede ver/editar su propio recurso (retrieve/partial_update).
    """
    def has_permission(self, request, view):
        # Para las acciones que no son objeto-específicas (list, create, etc.)
        if view.action in ("list", "create", "destroy"):
            return bool(request.user and request.user.is_authenticated and (request.user.is_staff or request.user.is_superuser))
        # Para retrieve/partial_update, permitimos pasar al has_object_permission
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        # Admin puede todo
        if request.user.is_staff or request.user.is_superuser:
            return True
        # Los usuarios normales sólo pueden ver/editar su propio usuario
        return obj.get("email") == getattr(request.user, "email", None) or getattr(obj, "id", None) == getattr(request.user, "id", None)


class UsuarioViewSet(viewsets.ViewSet):
    """
    ViewSet mínimo para gestionar usuarios (con persistencia en Supabase).
    Rutas soportadas:
      - POST /api/usuarios/        -> crea usuario (solo admin)
      - GET  /api/usuarios/        -> lista usuarios (solo admin)
      - GET  /api/usuarios/{pk}/   -> obtener usuario (admin o el propio usuario)
      - PATCH/PUT /api/usuarios/{pk}/ -> actualizar (admin o propio)
      - DELETE /api/usuarios/{pk}/ -> eliminar (solo admin)
    """
    permission_classes = [IsAdminUserOrReadSelf]

    def list(self, request):
        # Solo admin: listar todos los usuarios desde Supabase
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)

        resp = supabase.table("usuarios").select("*").execute()
        return Response(resp.data or [], status=status.HTTP_200_OK)

    def create(self, request):
        # Solo admin puede crear
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)

        serializer = UsuarioSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            usuario = serializer.save()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"message": "Usuario creado exitosamente", "usuario": usuario}, status=status.HTTP_201_CREATED)

    def retrieve(self, request, pk=None):
        # Obtener un usuario por id (o email como pk si lo prefieres)
        # Soporta que pk sea el id de Supabase (UUID) o email
        # Buscamos primero por id, luego por email
        q = supabase.table("usuarios").select("*").eq("id", pk).execute()
        data = q.data or []
        if not data:
            q = supabase.table("usuarios").select("*").eq("email", pk).execute()
            data = q.data or []
            if not data:
                return Response({"detail": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        usuario = data[0]
        # Permisos por objeto
        if not request.user.is_staff and not request.user.is_superuser:
            # Si no admin, solo puede ver su propio registro (comparar email)
            if usuario.get("email") != getattr(request.user, "email", None):
                return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)

        return Response(usuario, status=status.HTTP_200_OK)

    def partial_update(self, request, pk=None):
        # Admin puede actualizar todo; usuario normal solo puede actualizar ciertos campos de su perfil
        q = supabase.table("usuarios").select("*").eq("id", pk).execute()
        data = q.data or []
        if not data:
            return Response({"detail": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        usuario = data[0]

        # Si no admin, solo puede actualizar su propio usuario
        if not (request.user.is_staff or request.user.is_superuser):
            if usuario.get("email") != getattr(request.user, "email", None):
                return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)
            # No permitimos que el usuario normal cambie su rol ni el email
            forbidden = set(request.data.keys()) & {"rol", "email", "id"}
            if forbidden:
                return Response({"detail": "No autorizado para cambiar esos campos"}, status=status.HTTP_403_FORBIDDEN)

        # Validar email si se intenta cambiar
        if "email" in request.data:
            # check duplicate
            resp_check = supabase.table("usuarios").select("id").eq("email", request.data["email"]).execute()
            if resp_check.data:
                return Response({"email": ["El correo ya está en uso"]}, status=status.HTTP_400_BAD_REQUEST)

        # Ejecutar update en Supabase
        update_payload = request.data.copy()
        try:
            resp = supabase.table("usuarios").update(update_payload).eq("id", pk).execute()
        except Exception as e:
            return Response({"detail": f"Error al actualizar: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response(resp.data[0] if resp.data else {}, status=status.HTTP_200_OK)

    # ----------------------------
    # Escenario 1: Crear usuario con rol
    # ----------------------------
    @action(detail=False, methods=["post"], url_path="crear_con_rol")
    def crear_con_rol(self, request):
        """
        Crea un usuario y lo asigna a un grupo (rol) en Supabase.
        Solo administradores pueden ejecutar esta acción.
        """
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)

        data = request.data
        rol = data.get("rol")
        if not rol:
            return Response({"detail": "Debe especificar el rol"}, status=status.HTTP_400_BAD_REQUEST)

        # Crear usuario base
        serializer = UsuarioSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            usuario = serializer.save()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Buscar ID del grupo en Supabase
        group_res = supabase.table("auth_group").select("id").eq("name", rol).execute()
        if not group_res.data:
            return Response({"detail": f"El rol '{rol}' no existe"}, status=status.HTTP_404_NOT_FOUND)

        group_id = group_res.data[0]["id"]

        # Vincular usuario con grupo
        supabase.table("auth_user_groups").insert({
            "user_id": usuario["id"],
            "group_id": group_id
        }).execute()

        return Response({"message": f"Usuario '{usuario['email']}' creado con rol '{rol}'"}, status=status.HTTP_201_CREATED)

    # ----------------------------
    # Escenario 2: Actualizar rol de usuario
    # ----------------------------
    @action(detail=True, methods=["patch"], url_path="actualizar_rol")
    def actualizar_rol(self, request, pk=None):
        """
        Permite actualizar el rol de un usuario (solo administradores).
        """
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)

        nuevo_rol = request.data.get("rol")
        if not nuevo_rol:
            return Response({"detail": "Debe especificar el nuevo rol"}, status=status.HTTP_400_BAD_REQUEST)

        # Buscar ID del nuevo grupo
        group_res = supabase.table("auth_group").select("id").eq("name", nuevo_rol).execute()
        if not group_res.data:
            return Response({"detail": f"El rol '{nuevo_rol}' no existe"}, status=status.HTTP_404_NOT_FOUND)
        group_id = group_res.data[0]["id"]

        # Eliminar roles actuales
        supabase.table("auth_user_groups").delete().eq("user_id", pk).execute()
        # Asignar nuevo rol
        supabase.table("auth_user_groups").insert({
            "user_id": pk,
            "group_id": group_id
        }).execute()

        return Response({"message": f"Rol actualizado a '{nuevo_rol}'"}, status=status.HTTP_200_OK)

    # ----------------------------
    # Escenario 3: Consultar roles del usuario
    # ----------------------------
    @action(detail=True, methods=["get"], url_path="roles")
    def obtener_roles(self, request, pk=None):
        """
        Devuelve los roles asignados al usuario.
        Admin puede consultar cualquier usuario;
        usuario normal solo puede consultar su propio rol.
        """
        if not (request.user.is_staff or request.user.is_superuser):
            # Validar que el usuario solo pida sus propios datos
            if str(getattr(request.user, "id", "")) != str(pk):
                return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)

        res = (
            supabase.table("auth_user_groups")
            .select("group_id, auth_group(name)")
            .eq("user_id", pk)
            .execute()
        )

        if not res.data:
            return Response({"roles": []}, status=status.HTTP_200_OK)

        roles = [r["auth_group"]["name"] for r in res.data if "auth_group" in r]
        return Response({"roles": roles}, status=status.HTTP_200_OK)


    def destroy(self, request, pk=None):
        """
        Elimina un usuario y sus relaciones (solo administradores).
        """
        if not (request.user.is_staff or request.user.is_superuser):
            return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)

        try:
            # Eliminar relaciones de roles primero
            supabase.table("auth_user_groups").delete().eq("user_id", pk).execute()
            # Eliminar usuario
            supabase.table("usuarios").delete().eq("id", pk).execute()
        except Exception as e:
            return Response({"detail": f"Error al eliminar: {e}"}, status=status.HTTP_400_BAD_REQUEST)

        return Response({"message": "Usuario eliminado correctamente"}, status=status.HTTP_204_NO_CONTENT)

        

def home(request):
    return HttpResponse("¡Hola, Django está funcionando correctamente!")


class RegisterView(APIView):
    """
    Vista pública para registro de usuarios (auto-registro).
    - Permite que cualquier persona cree una cuenta básica.
    - El rol siempre se establece como 'Usuario' (no puede ser asignado por el cliente).
    """
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        data = request.data.copy()
        # Forzar rol por defecto
        data.pop("role", None)
        data["role"] = "Usuario"

        serializer = UserSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = serializer.save()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Devolver representación del usuario (sin password)
        out = UserSerializer(user).data
        return Response(out, status=status.HTTP_201_CREATED)


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Permite login con username o email y añade info de usuario/grupos en la respuesta."""
    def validate(self, attrs):
        # Permitir login con username o email
        username_or_email = attrs.get("username")
        password = attrs.get("password")
        UserModel = get_user_model()

        # Buscar usuario por username o email
        user = None
        if username_or_email:
            try:
                user = UserModel.objects.filter(username=username_or_email).first()
                if not user:
                    user = UserModel.objects.filter(email=username_or_email).first()
            except Exception:
                pass

        if not user:
            # Si no se encuentra, lanzar error estándar
            from rest_framework_simplejwt.exceptions import AuthenticationFailed
            raise AuthenticationFailed("No se encontró usuario con ese username o email.")

        # Reemplazar username en attrs por el username real para que SimpleJWT lo valide
        attrs["username"] = user.username

        data = super().validate(attrs)
        self.user = user
        try:
            groups = [g.name for g in user.groups.all()]
        except Exception:
            groups = []

        data.update({
            "user": {
                "id": user.id,
                "username": getattr(user, "username", ""),
                "email": getattr(user, "email", ""),
                "first_name": getattr(user, "first_name", ""),
                "last_name": getattr(user, "last_name", ""),
                "groups": groups,
            }
        })
        return data


class CustomTokenObtainPairView(TokenObtainPairView):
    """Vista que usa el serializer personalizado para devolver tokens + info de usuario."""
    serializer_class = CustomTokenObtainPairSerializer
