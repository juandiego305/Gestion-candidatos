# core/views.py
from django.http import HttpResponse
from django.contrib.auth import get_user_model
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.views import APIView
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.conf import settings
from .serializers_user import PerfilSerializer, UserSerializer
from .models import Empresa
from .serializers import EmpresaSerializer, UsuarioSerializer, supabase
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import Roles
from supabase import create_client
from rest_framework import generics, permissions
from django.http import JsonResponse
from rest_framework.decorators import api_view
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .models import Vacante, Empresa
from .serializers import VacanteSerializer
from datetime import datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404





supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)

def get_supabase_role(user):
    """
    Obtiene el campo 'role' desde la tabla auth_user de Supabase
    usando el id del usuario de Django.
    """
    try:
        resp = supabase.table("auth_user").select("role").eq("id", user.id).execute()
        if resp.data and len(resp.data) > 0:
            role = resp.data[0].get("role")
            print("🔥 Rol desde Supabase:", role)
            return role
        else:
            print("⚠️ Usuario no encontrado en Supabase para id:", user.id)
            return None
    except Exception as e:
        print("⚠️ Error obteniendo rol de Supabase:", e)
        return None

User = get_user_model()

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def crear_vacante(request):

    # 1. Obtener rol desde Supabase
    role = get_supabase_role(request.user)
    print("🔥 Rol obtenido desde Supabase:", role)

    if role != 'admin':
        return JsonResponse(
            {'error': 'Solo un administrador puede crear vacantes.'},
            status=403
        )

    data = request.data

    titulo = data.get('titulo')
    descripcion = data.get('descripcion')
    requisitos = data.get('requisitos')
    fecha_expiracion_str = data.get('fecha_expiracion')
    empresa_id = data.get('empresa_id')

    if not all([titulo, descripcion, requisitos, fecha_expiracion_str, empresa_id]):
        return JsonResponse({'error': 'Todos los campos son requeridos.'}, status=400)

    # 2. Convertir fecha naive -> aware
    try:
        fecha_naive = datetime.fromisoformat(fecha_expiracion_str)
        fecha_expiracion = timezone.make_aware(fecha_naive, timezone.get_current_timezone())

        if fecha_expiracion < timezone.now():
            return JsonResponse({'error': 'La fecha de expiración no puede ser en el pasado.'}, status=400)

    except Exception:
        return JsonResponse({'error': 'Formato de fecha inválido. Usa YYYY-MM-DDTHH:MM:SS'}, status=400)

    # 3. Validar empresa
    try:
        empresa = Empresa.objects.get(id=empresa_id)
    except Empresa.DoesNotExist:
        return JsonResponse({'error': 'La empresa especificada no existe.'}, status=400)

    # 4. Crear vacante
    vacante = Vacante.objects.create(
        titulo=titulo,
        descripcion=descripcion,
        requisitos=requisitos,
        fecha_expiracion=fecha_expiracion,
        id_empresa=empresa,
        creado_por=request.user,
    )

    return JsonResponse(
        {'message': 'Vacante creada exitosamente', 'vacante_id': vacante.id},
        status=201
    )



@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated])
def actualizar_vacante(request, vacante_id):
    # 1. Verificar rol
    role = get_supabase_role(request.user)
    if role != 'admin':
        return JsonResponse(
            {'error': 'Solo los administradores pueden actualizar vacantes.'},
            status=403
        )

    # 2. Obtener la vacante o 404
    vacante = get_object_or_404(Vacante, id=vacante_id)

    data = request.data

    # 3. Actualizar campos solo si vienen en el body
    titulo = data.get('titulo')
    descripcion = data.get('descripcion')
    requisitos = data.get('requisitos')
    fecha_expiracion_str = data.get('fecha_expiracion')
    estado = data.get('estado')

    if titulo is not None:
        vacante.titulo = titulo

    if descripcion is not None:
        vacante.descripcion = descripcion

    if requisitos is not None:
        vacante.requisitos = requisitos

    if estado is not None:
        # Solo permitir valores válidos
        if estado not in ['Borrador', 'Publicado']:
            return JsonResponse(
                {'error': 'Estado inválido. Use "Borrador" o "Publicado".'},
                status=400
            )
        vacante.estado = estado

    if fecha_expiracion_str is not None:
        try:
            fecha_naive = datetime.fromisoformat(fecha_expiracion_str)
            fecha_expiracion = timezone.make_aware(
                fecha_naive,
                timezone.get_current_timezone()
            )
        except ValueError:
            return JsonResponse(
                {'error': 'Formato de fecha_expiracion inválido. Use ISO 8601.'},
                status=400
            )

        if fecha_expiracion < timezone.now():
            return JsonResponse(
                {'error': 'La fecha de expiración no puede ser en el pasado.'},
                status=400
            )

        vacante.fecha_expiracion = fecha_expiracion

    vacante.save()

    return JsonResponse({
        'message': 'Vacante actualizada correctamente',
        'vacante': {
            'id': vacante.id,
            'titulo': vacante.titulo,
            'descripcion': vacante.descripcion,
            'requisitos': vacante.requisitos,
            'fecha_expiracion': vacante.fecha_expiracion,
            'estado': vacante.estado,
            'empresa_id': vacante.id_empresa_id,
        }
    }, status=200)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated])
def eliminar_vacante(request, vacante_id):
    # 1. Verificar rol
    role = get_supabase_role(request.user)
    if role != 'admin':
        return JsonResponse(
            {'error': 'Solo los administradores pueden eliminar vacantes.'},
            status=403
        )

    # 2. Obtener la vacante o 404
    vacante = get_object_or_404(Vacante, id=vacante_id)

    vacante.delete()

    return JsonResponse(
        {'message': f'Vacante {vacante_id} eliminada correctamente.'},
        status=200
    )

@api_view(['PATCH'])
@permission_classes([IsAuthenticated])
def publicar_vacante(request, vacante_id):
    # 1. Verificar rol
    role = get_supabase_role(request.user)
    if role != 'admin':
        return JsonResponse(
            {'error': 'Solo los administradores pueden publicar vacantes.'},
            status=403
        )

    # 2. Obtener la vacante o 404
    vacante = get_object_or_404(Vacante, id=vacante_id)

    # 3. Validar fecha de expiración
    if vacante.fecha_expiracion and vacante.fecha_expiracion < timezone.now():
        return JsonResponse(
            {'error': 'No se puede publicar una vacante con fecha de expiración pasada.'},
            status=400
        )

    vacante.estado = 'Publicado'
    vacante.save()

    return JsonResponse({
        'message': 'Vacante publicada correctamente.',
        'vacante': {
            'id': vacante.id,
            'titulo': vacante.titulo,
            'estado': vacante.estado,
            'fecha_expiracion': vacante.fecha_expiracion,
        }
    }, status=200)

@api_view(['GET'])
@permission_classes([IsAuthenticated])
def listar_vacantes(request):
    """
    Lista vacantes según el rol del usuario.

    - Admin:
        - Si envía ?empresa_id=X → solo esa empresa.
        - Si no envía → todas las vacantes.
    - Empleado RRHH:
        - Siempre solo las vacantes de SU empresa (ignora empresa_id del query).
    - Candidato:
        - Solo vacantes en estado "Publicado".
        - Si envía ?empresa_id=X → solo publicadas de esa empresa.
    """
    role = get_supabase_role(request.user)
    empresa_param = request.GET.get("empresa_id")

    # --- ADMIN: ve todas o filtra por empresa_id si viene en el query ---
    if role == "admin":
        if empresa_param:
            vacantes = Vacante.objects.filter(id_empresa_id=empresa_param)
        else:
            vacantes = Vacante.objects.all()

    # --- EMPLEADO_RRHH: ve solo las de su empresa (ignora empresa_param) ---
    elif role == "empleado_rrhh":
        try:
            empresa_id = Empresa.objects.get(owner=request.user).id
        except Empresa.DoesNotExist:
            return JsonResponse(
                {"error": "No tienes una empresa asociada."},
                status=400
            )
        vacantes = Vacante.objects.filter(id_empresa_id=empresa_id)

    # --- CANDIDATO: solo vacantes publicadas, con filtro opcional por empresa ---
    else:
        vacantes = Vacante.objects.filter(estado="Publicado")
        if empresa_param:
            vacantes = vacantes.filter(id_empresa_id=empresa_param)

    data = []
    for v in vacantes:
        data.append({
            "id": v.id,
            "titulo": v.titulo,
            "descripcion": v.descripcion,
            "requisitos": v.requisitos,
            "fecha_expiracion": v.fecha_expiracion,
            "estado": v.estado,
            "empresa_id": v.id_empresa_id,
            "empresa_nombre": v.id_empresa.nombre,
        })

    return JsonResponse(data, safe=False, status=200)
# ----------------------------
# Permisos
# ----------------------------
class IsOwner(permissions.BasePermission):
    """Permite acceso solo al propietario de la empresa."""
    def has_object_permission(self, request, view, obj):
        return obj.owner_id == request.user.id


class IsAdmin(permissions.BasePermission):
    """Solo administradores pueden gestionar usuarios"""
    def has_permission(self, request, view):
        return request.user and request.user.role == 'admin'


class IsAdminUserOrReadSelf(permissions.BasePermission):
    """
    Permiso compuesto:
    - Admin: puede listar, crear, actualizar y eliminar usuarios.
    - Usuario normal: solo puede ver y editar su propio perfil.
    """
    def has_permission(self, request, view):
        if view.action in ("list", "create", "destroy"):
            return bool(request.user and request.user.is_authenticated and request.user.role == "admin")
        return bool(request.user and request.user.is_authenticated)

    def has_object_permission(self, request, view, obj):
        if request.user.role == "admin":
            return  obj.empresa_id == request.user.empresa_id
        return obj.get("email") == getattr(request.user, "email", None) or getattr(obj, "id", None) == getattr(request.user, "id", None)


# ----------------------------
# Home
# ----------------------------
def home(request):
    return HttpResponse("¡Hola, Django está funcionando correctamente!")


# ----------------------------
# Registro de usuarios
# ----------------------------
class RegisterView(APIView):
    """Registro público de usuarios (rol por defecto: candidato)"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        data = request.data.copy()
        data.pop("role", None)
        data["role"] = Roles.CANDIDATO  # rol por defecto

        serializer = UserSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = serializer.create(data)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        out = UserSerializer(user).data
        return Response(out, status=status.HTTP_201_CREATED)


# ----------------------------
# Login con JWT
# ----------------------------
from .serializers import supabase

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Login con username o email + devolver info de usuario y grupos"""
    def validate(self, attrs):
        username_or_email = attrs.get("username")
        password = attrs.get("password")
        UserModel = get_user_model()

        # Buscar usuario por username o email
        user = UserModel.objects.filter(username=username_or_email).first() or UserModel.objects.filter(email=username_or_email).first()
        if not user:
            from rest_framework_simplejwt.exceptions import AuthenticationFailed
            raise AuthenticationFailed("No se encontró usuario con ese username o email.")

        attrs["username"] = user.username  # necesario para JWT

        # Validar token JWT normalmente
        data = super().validate(attrs)
        self.user = user

        # Buscar el rol en Supabase por email
        try:
            sup_user = supabase.table("auth_user").select("role").eq("id", user.id).execute()
            if sup_user.data:
                role = sup_user.data[0].get("role", "candidato")
            else:
                     role = "candidato"
        except Exception as e:
            print(f"⚠️ Error obteniendo rol de Supabase: {e}")
            role = "candidato"

        # Obtener grupos (si los usas)
        groups = [g.name for g in user.groups.all()] if hasattr(user, "groups") else []

        # Devolver el payload completo
        data.update({
            "user": {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "role": role,
                "groups": groups
            }
        })
        return data

class CustomTokenObtainPairView(TokenObtainPairView):
    serializer_class = CustomTokenObtainPairSerializer
# ----------------------------
# Empresa
# ----------------------------
class EmpresaViewSet(viewsets.ModelViewSet):
    serializer_class = EmpresaSerializer
    permission_classes = [permissions.IsAuthenticated, IsOwner]

    def get_queryset(self):
        # Solo muestra las empresas del usuario autenticado
        return Empresa.objects.filter(owner=self.request.user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def perform_create(self, serializer):
        """
        Cuando un usuario crea una empresa:
        1️⃣ Se guarda la empresa con su usuario como owner.
        2️⃣ Se actualiza su rol en Django.
        3️⃣ Se sincroniza el rol y grupo 'admin' en Supabase.
        """
        user = self.request.user

        # Crear empresa vinculada al usuario autenticado
        empresa = serializer.save(owner=user)

        # --- 1️⃣ Actualizar rol en Django ---
        if hasattr(user, "role"):
            user.role = "admin"
            user.save(update_fields=["role"])
            print(f"✅ Rol del usuario '{user.username}' actualizado a ADMIN en Django")

        # --- 2️⃣ Sincronizar con Supabase ---
        try:
            # Buscar el usuario en Supabase por email
            sup_user = supabase.table("auth_user").select("id").eq("email", user.email).execute()

            if not sup_user.data:
                print(f"⚠️ Usuario {user.email} no encontrado en Supabase.")
                return

            user_id = sup_user.data[0]["id"]

            # 🔹 Actualizar rol en la tabla usuarios
            supabase.table("auth_user").update({"role": "admin"}).eq("id", user_id).execute()
            print(f"✅ Rol de {user.email} actualizado a 'admin' en Supabase.")

            # 🔹 Obtener ID del grupo 'admin'
            group_res = supabase.table("auth_group").select("id").eq("name", "admin").execute()
            if not group_res.data:
                print("⚠️ El grupo 'admin' no existe en Supabase.")
                return

            group_id = group_res.data[0]["id"]

            # 🔹 Eliminar grupos anteriores del usuario
            supabase.table("auth_user_groups").delete().eq("user_id", user_id).execute()

            # 🔹 Asignar grupo admin
            supabase.table("auth_user_groups").insert({
                "user_id": user_id,
                "group_id": group_id
            }).execute()

            print(f"✅ Usuario {user.email} asignado correctamente al grupo 'admin' en Supabase.")

        except Exception as e:
            print(f"⚠️ Error actualizando rol en Supabase: {e}")
            return empresa

# ----------------------------
# Usuarios
# ----------------------------
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("-id")
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin]


class UsuarioViewSet(viewsets.ViewSet):
    """
    Gestión de usuarios con Supabase.
    """
    permission_classes = [IsAdminUserOrReadSelf]

    def list(self, request):
        if request.user.role != "admin":
            return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)
        resp = supabase.table("usuarios").select("*").execute()
        return Response(resp.data or [], status=status.HTTP_200_OK)

    def create(self, request):
        if request.user.role != "admin":
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
        q = supabase.table("usuarios").select("*").eq("id", pk).execute()
        data = q.data or []
        if not data:
            return Response({"detail": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        usuario = data[0]
        if request.user.role != "admin" and usuario.get("email") != request.user.email:
            return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)
        return Response(usuario, status=status.HTTP_200_OK)

    def partial_update(self, request, pk=None):
        q = supabase.table("usuarios").select("*").eq("id", pk).execute()
        data = q.data or []
        if not data:
            return Response({"detail": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        usuario = data[0]

        if request.user.role != "admin" and usuario.get("email") != request.user.email:
            return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)
            forbidden = set(request.data.keys()) & {"rol", "email", "id"}
            if forbidden:
                return Response({"detail": "No autorizado para cambiar esos campos"}, status=status.HTTP_403_FORBIDDEN)

        update_payload = request.data.copy()
        try:
            resp = supabase.table("usuarios").update(update_payload).eq("id", pk).execute()
        except Exception as e:
            return Response({"detail": f"Error al actualizar: {e}"}, status=status.HTTP_400_BAD_REQUEST)
        return Response(resp.data[0] if resp.data else {}, status=status.HTTP_200_OK)

    @action(detail=False, methods=["post"], url_path="crear_con_rol")
    def crear_con_rol(self, request):
        if request.user.role != "admin":
            return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)
        data = request.data
        rol = data.get("rol")
        if not rol:
            return Response({"detail": "Debe especificar el rol"}, status=status.HTTP_400_BAD_REQUEST)
        serializer = UsuarioSerializer(data=data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            usuario = serializer.save()
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        group_res = supabase.table("auth_group").select("id").eq("name", rol).execute()
        if not group_res.data:
            return Response({"detail": f"El rol '{rol}' no existe"}, status=status.HTTP_404_NOT_FOUND)
        group_id = group_res.data[0]["id"]

        supabase.table("auth_user_groups").insert({"user_id": usuario["id"], "group_id": group_id}).execute()
        return Response({"message": f"Usuario '{usuario['email']}' creado con rol '{rol}'"}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path="actualizar_rol")
    def actualizar_rol(self, request, pk=None):
        if request.user.role != "admin":
            return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)
        nuevo_rol = request.data.get("rol")
        if not nuevo_rol:
            return Response({"detail": "Debe especificar el nuevo rol"}, status=status.HTTP_400_BAD_REQUEST)
        group_res = supabase

    
    # ----------------------------
# Reset de contraseña
# ----------------------------
class PasswordResetRequestView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get("email")
        if not email:
            return Response({"error": "Debe enviar un correo"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            user = User.objects.get(email=email)
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            reset_link = f"http://localhost:3000/reset-password/{uid}/{token}/"

            send_mail(
                subject="Resetear contraseña",
                message=f"Usa este enlace para resetear tu contraseña: {reset_link}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                fail_silently=False,
            )
            return Response({"message": "Correo enviado correctamente"})
        except User.DoesNotExist:
            return Response({"error": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        
        
class PasswordResetConfirmView(APIView):
    permission_classes = []

    def post(self, request, uidb64, token):
        password = request.data.get("password")
        if not password:
            return Response({"detail": "Se requiere nueva contraseña"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({"detail": "Enlace inválido"}, status=status.HTTP_400_BAD_REQUEST)

        if not default_token_generator.check_token(user, token):
            return Response({"detail": "Token inválido o expirado"}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(password)
        user.save()
        return Response({"detail": "Contraseña restablecida correctamente"}, status=status.HTTP_200_OK)
    

class PerfilView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user = request.user
        # Buscar usuario en Supabase usando el email o el ID
        response = supabase.table("auth_user").select("*").eq("email", user.email).execute()

        if not response.data:
            return Response({"error": "Usuario no encontrado en Supabase"}, status=404)

        perfil = response.data[0]

         # Filtrar solo los campos que deseas mostrar
        datos_filtrados = {
            "id": perfil.get("id"),
            "username": perfil.get("username"),
            "first_name": perfil.get("first_name"),
            "last_name": perfil.get("last_name"),
            "email": perfil.get("email"),
            "role": perfil.get("role"),
            "date_joined": perfil.get("date_joined"),
            "last_login": perfil.get("last_login"),
        }

        return Response(datos_filtrados)
