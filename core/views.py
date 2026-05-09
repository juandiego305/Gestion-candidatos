# core/views.py
from django.http import HttpResponse
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import viewsets, permissions, status
from rest_framework.response import Response
from rest_framework.decorators import action
from rest_framework.views import APIView
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from urllib.parse import urlencode
from django.contrib.auth.tokens import default_token_generator
from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
import os



from .serializers_user import PerfilSerializer, UserSerializer
from .models import Empresa, Entrevista, Postulacion, VacanteRRHH

from .serializers_user import PerfilSerializer, UserSerializer, PerfilUsuarioSerializer
from .models import Empresa

from .serializers import EmpresaSerializer, UsuarioSerializer, PostulacionSerializer, EntrevistaSerializer
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import Roles
from .email_service import send_plain_email, send_template_email, send_message_async

from rest_framework import generics, permissions

from django.http import JsonResponse
from rest_framework.decorators import api_view
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .serializers import VacanteSerializer
from datetime import datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from .middleware import CheckUserInactivityPermission
from django.shortcuts import get_object_or_404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import Vacante, Postulacion, Empresa
import logging
from .models import Favorito
from .serializers import FavoritoSerializer
from django.db.models import Count, Max
from django.db import transaction
from django.db import connection
import io
import csv
import time
import os
from io import BytesIO
import cloudinary
import cloudinary.api
import cloudinary.uploader

logger = logging.getLogger(__name__)

if os.getenv("CLOUDINARY_URL"):
    cloudinary.config(cloudinary_url=os.getenv("CLOUDINARY_URL"), secure=True)


def _upload_to_cloudinary(file_bytes, folder, filename, resource_type="auto"):
    ts = int(time.time())
    original = (filename or "file").replace(" ", "_")
    stem, ext = (original.rsplit(".", 1) + [""])[:2] if "." in original else (original, "")

    # En uploads no-raw, Cloudinary añade formato en URL; evitar .pdf.pdf.
    if resource_type == "raw" and ext:
        name = f"{stem}_{ts}.{ext}"
    else:
        name = f"{stem}_{ts}"

    public_id = f"{folder}/{name}"
    result = cloudinary.uploader.upload(
        io.BytesIO(file_bytes),
        public_id=public_id,
        resource_type=resource_type,
        overwrite=True,
        invalidate=True,
    )
    return result.get("secure_url") or result.get("url")





def get_supabase_role(user):
    """Obtiene el rol del usuario desde la BD (prioriza SQL raw sobre atributo en memoria)"""
    # Primero intentar leer directamente de la BD para asegurar que esté actualizado
    from django.db import connection
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT role FROM auth_user WHERE id = %s', [user.id])
            row = cursor.fetchone()
            if row and row[0]:
                return normalize_role(row[0])
    except Exception:
        pass
    
    # Fallback a atributo en memoria
    role = getattr(user, "role", None)
    if role:
        return normalize_role(role)

    # Fallback a grupos de Django
    group_names = {g.name.lower() for g in user.groups.all()}
    if "admin" in group_names:
        return Roles.ADMIN
    if "empleado_rrhh" in group_names or "rrhh" in group_names:
        return Roles.EMPLEADO_RRHH
    return Roles.CANDIDATO


def normalize_role(role):
    """
    Normaliza variantes posibles del rol desde Supabase o desde el atributo Django
    y devuelve la forma canónica utilizada en la aplicación.
    """
    if not role:
        return None
    r = str(role).strip().lower()
    # Mapear variantes comunes a los roles canónicos
    if r in ("admin", "administrator", "owner"):
        return Roles.ADMIN
    if r in ("rrhh", "recursos humanos", "recursoshumanos", "empleado_rrhh", "empleado-rrhh", "rrhh_empleado"):
        return Roles.EMPLEADO_RRHH
    if r in ("candidato", "candidate"):
        return Roles.CANDIDATO
    return r


def get_supabase_empresa_id(user):
    # 1) Empresa asignada directamente al usuario (RRHH/candidato promovido).
    assigned_empresa = getattr(user, "id_empresa", None)
    if assigned_empresa:
        return assigned_empresa

    # 2) Fallback a columna real en auth_user cuando el modelo no expone el campo.
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT id_empresa FROM auth_user WHERE id = %s", [user.id])
            row = cursor.fetchone()
            if row and row[0]:
                return row[0]
    except Exception:
        pass

    # 3) Si es owner de empresa (admin dueño), usar esa empresa.
    owned_empresa = Empresa.objects.filter(owner=user).values_list("id", flat=True).first()
    return owned_empresa

from .models import PerfilUsuario, validate_hoja_vida
from rest_framework import status, permissions, parsers 
import time


User = get_user_model()

@api_view(['POST'])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
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
    ubicacion = data.get('ubicacion')
    salario = data.get('salario')
    experiencia = data.get('experiencia')
    beneficios = data.get('beneficios')
    tipo_jornada = data.get('tipo_jornada')
    modalidad_trabajo = data.get('modalidad_trabajo')  # Hibrido / Remoto / Presencial

    if not all([titulo, descripcion, requisitos, fecha_expiracion_str, empresa_id]):
        return JsonResponse({'error': 'Título, descripción, requisitos, fecha_expiracion y empresa_id son obligatorios.'}, status=400)
    
    MODALIDADES_VALIDAS = ["Hibrido", "Remoto", "Presencial"]
    if modalidad_trabajo and modalidad_trabajo not in MODALIDADES_VALIDAS:
        return JsonResponse(
            {'error': f"modalidad_trabajo debe ser una de: {', '.join(MODALIDADES_VALIDAS)}"},
            status=400
        )

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
    try:
        vacante = Vacante.objects.create(
            titulo=titulo,
            descripcion=descripcion,
            requisitos=requisitos,
            fecha_expiracion=fecha_expiracion,
            id_empresa=empresa,
            creado_por=request.user,
            ubicacion=ubicacion,
            salario=salario or None,
            experiencia=experiencia,
            beneficios=beneficios,
            tipo_jornada=tipo_jornada,
            modalidad_trabajo=modalidad_trabajo,
        )
    except Exception as e:
        logger.exception("Error creando vacante")
        detail = str(e) if settings.DEBUG else "Error interno al crear vacante"
        return JsonResponse(
            {
                "error": "No se pudo crear la vacante.",
                "detail": detail,
                "hint": "Verifica migraciones pendientes con 'python manage.py migrate'.",
            },
            status=500,
        )

    return JsonResponse(
        {'message': 'Vacante creada exitosamente', 'vacante_id': vacante.id},
        status=201
    )

# ----------------------------
# Asignar empleado a empresa
# ----------------------------
class AsignarEmpleadoView(APIView):

    def post(self, request):
        empresa_id = request.data.get("empresa_id")
        email = request.data.get("email")

        if not empresa_id or not email:
            return Response(
                {"error": "Debe enviar 'empresa_id' y 'email'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # --- 1. Verificar empresa ---
        try:
            empresa = Empresa.objects.get(id=empresa_id)
        except Empresa.DoesNotExist:
            return Response(
                {"error": "La empresa no existe."},
                status=status.HTTP_404_NOT_FOUND
            )

        # --- 2. Verificar que la empresa pertenece al usuario logueado ---
        if empresa.owner_id != request.user.id:
            return Response(
                {"error": "No tiene permisos para asignar empleados a esta empresa."},
                status=status.HTTP_403_FORBIDDEN
            )

        # --- 3. Buscar usuario por email en Django ---
        try:
            empleado = User.objects.filter(email=email).first()
            if not empleado:
                return Response(
                    {"error": "No existe un usuario con ese correo."},
                    status=status.HTTP_404_NOT_FOUND
                )

        except Exception as e:
            return Response(
                {"error": f"Error consultando usuario: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        role = normalize_role(getattr(empleado, "role", None) or get_supabase_role(empleado))
        id_empresa_actual = getattr(empleado, "id_empresa", None)
        if id_empresa_actual is None:
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT id_empresa FROM auth_user WHERE id = %s", [empleado.id])
                    row = cursor.fetchone()
                    if row:
                        id_empresa_actual = row[0]
            except Exception:
                id_empresa_actual = None

        # --- 4. Validar rol candidato ---
        if role != "candidato":
            return Response(
                {"error": "Solo se pueden asignar usuarios con rol 'candidato'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # --- 5. Validar que no esté asignado ya ---
        if id_empresa_actual:
            return Response(
                {"error": "Este usuario ya está asignado a una empresa."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # --- 6. Asignar empresa al usuario ---
        try:
            with transaction.atomic():
                # Camino principal: escribir directo en auth_user (fuente real de verdad en este proyecto).
                with connection.cursor() as cursor:
                    cursor.execute(
                        "UPDATE auth_user SET role = %s, id_empresa = %s WHERE id = %s",
                        [Roles.EMPLEADO_RRHH, empresa.id, empleado.id],
                    )

                # Respaldo ORM por compatibilidad si el modelo expone esos campos.
                update_fields = []
                if hasattr(empleado, "id_empresa"):
                    empleado.id_empresa = empresa.id
                    update_fields.append("id_empresa")
                if hasattr(empleado, "role"):
                    empleado.role = Roles.EMPLEADO_RRHH
                    update_fields.append("role")
                if update_fields:
                    empleado.save(update_fields=update_fields)

                rrhh_group, _ = Group.objects.get_or_create(name=Roles.EMPLEADO_RRHH)
                empleado.groups.add(rrhh_group)

        except Exception as e:
            logger.exception("Error actualizando empleado durante asignacion")
            detail = str(e) if settings.DEBUG else "Error interno"
            return Response(
                {
                    "error": "Error actualizando usuario durante la asignacion.",
                    "detail": detail,
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response(
            {
                "message": "Empleado asignado correctamente.",
                "empresa_id": empresa.id,
                "email": email
            },
            status=status.HTTP_200_OK
        )

@api_view(['GET'])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
def listar_trabajadores(request, empresa_id):

    # 1) Validar rol del usuario logueado
    admin_role = get_supabase_role(request.user)
    if admin_role != "admin":
        return Response({"error": "Solo un administrador puede ver esta información."}, status=403)

    # 2) Validar que la empresa pertenezca al admin
    try:
        empresa = Empresa.objects.get(id=empresa_id, owner_id=request.user.id)
    except Empresa.DoesNotExist:
        return Response({"error": "No tiene permisos sobre esta empresa."}, status=403)

    # 3) Obtener RRHH desde Django
    rrhh_users = User.objects.filter(groups__name__in=["rrhh", Roles.EMPLEADO_RRHH]).distinct()
    trabajadores = []
    for u in rrhh_users:
        user_empresa_id = getattr(u, "id_empresa", None)
        if user_empresa_id and int(user_empresa_id) != int(empresa_id):
            continue
        trabajadores.append({
            "id": u.id,
            "email": u.email,
            "role": normalize_role(getattr(u, "role", None)) or Roles.EMPLEADO_RRHH,
            "id_empresa": user_empresa_id,
        })

    return Response({
        "empresa": empresa.nombre,
        "empresa_id": empresa.id,
        "total_trabajadores": len(trabajadores),
        "trabajadores": trabajadores
    }, status=200)

@api_view(["GET"])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
def obtener_vacante(request, vacante_id):
    vacante = get_object_or_404(Vacante, id=vacante_id)
    serializer = VacanteSerializer(vacante)
    return Response(serializer.data, status=status.HTTP_200_OK)

@api_view(['PUT', 'PATCH'])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
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

    # Nuevos campos
    ubicacion = data.get('ubicacion')
    salario = data.get('salario')
    experiencia = data.get('experiencia')
    beneficios = data.get('beneficios')
    tipo_jornada = data.get('tipo_jornada')
    modalidad_trabajo = data.get('modalidad_trabajo')

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

    # 🔹 Actualizar campos nuevos si vienen
    if ubicacion is not None:
        vacante.ubicacion = ubicacion

    if salario is not None:
        vacante.salario = salario  # Django lo castea a Decimal si el modelo es DecimalField

    if experiencia is not None:
        vacante.experiencia = experiencia

    if beneficios is not None:
        vacante.beneficios = beneficios

    if tipo_jornada is not None:
        vacante.tipo_jornada = tipo_jornada

    if modalidad_trabajo is not None:
        MODALIDADES_VALIDAS = ["Hibrido", "Remoto", "Presencial"]
        if modalidad_trabajo not in MODALIDADES_VALIDAS:
            return JsonResponse(
                {'error': f'modalidad_trabajo debe ser una de: {", ".join(MODALIDADES_VALIDAS)}'},
                status=400
            )
        vacante.modalidad_trabajo = modalidad_trabajo

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

            'ubicacion': vacante.ubicacion,
            'salario': str(vacante.salario) if vacante.salario is not None else None,
            'experiencia': vacante.experiencia,
            'beneficios': vacante.beneficios,
            'tipo_jornada': vacante.tipo_jornada,
            'modalidad_trabajo': vacante.modalidad_trabajo,
        }
    }, status=200)


@api_view(['DELETE'])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
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
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
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
            'descripcion': vacante.descripcion,
            'requisitos': vacante.requisitos,
            'fecha_expiracion': vacante.fecha_expiracion,
            'estado': vacante.estado,
            'empresa_id': vacante.id_empresa_id,
            'empresa_nombre': vacante.id_empresa.nombre,

            'ubicacion': vacante.ubicacion,
            'salario': str(vacante.salario) if vacante.salario is not None else None,
            'experiencia': vacante.experiencia,
            'beneficios': vacante.beneficios,
            'tipo_jornada': vacante.tipo_jornada,
            'modalidad_trabajo': vacante.modalidad_trabajo,
        }
    }, status=200)

@api_view(['GET'])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
def listar_vacantes(request):
    """
    Lista vacantes según el rol del usuario.

    - Admin:
        - Si envía ?empresa_id=X → solo esa empresa.
        - Si no envía → todas las vacantes.
    - Empleado RRHH y Candidato:
        - Siempre ven vacantes en estado "Publicado" (de cualquier empresa).
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

    # --- EMPLEADO_RRHH y CANDIDATO: vacantes publicadas globales ---
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
            "ubicacion": v.ubicacion,
            "salario": str(v.salario) if v.salario is not None else None,
            "experiencia": v.experiencia,
            "beneficios": v.beneficios,
            "tipo_jornada": v.tipo_jornada,
            "modalidad_trabajo": v.modalidad_trabajo,
        })

    return JsonResponse(data, safe=False, status=200)


# ----------------------------
# Mis vacantes asignadas (RRHH)
# ----------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
def mis_vacantes_asignadas(request):
    """Devuelve las vacantes a las que el RRHH autenticado fue asignado.

    Requiere rol RRHH. Acepta tanto usuarios con rol en Django como los que tienen
    el rol en Supabase (se normaliza).
    """
    caller_role = normalize_role(getattr(request.user, 'role', None) or get_supabase_role(request.user))
    if caller_role != Roles.EMPLEADO_RRHH:
        return Response({'error': 'Solo usuarios RRHH pueden ver sus vacantes asignadas.'}, status=status.HTTP_403_FORBIDDEN)

    asignaciones = VacanteRRHH.objects.filter(rrhh_user=request.user).select_related('vacante', 'vacante__id_empresa')

    out = []
    for a in asignaciones:
        v = a.vacante
        out.append({
            'asignacion_id': a.id,
            'fecha_asignacion': a.fecha_asignacion,
            'vacante': {
                'id': v.id,
                'titulo': v.titulo,
                'descripcion': v.descripcion,
                'requisitos': v.requisitos,
                'fecha_expiracion': v.fecha_expiracion,
                'estado': v.estado,
                'empresa_id': v.id_empresa_id,
                'empresa_nombre': v.id_empresa.nombre if v.id_empresa else None,
                'ubicacion': v.ubicacion,
                'salario': str(v.salario) if v.salario is not None else None,
                'experiencia': v.experiencia,
                'beneficios': v.beneficios,
                'tipo_jornada': v.tipo_jornada,
                'modalidad_trabajo': v.modalidad_trabajo,
            }
        })

    return JsonResponse(out, safe=False, status=200)

# ----------------------------
# Postulacion
# ----------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
def postular_vacante(request, vacante_id):

    # 1) Validar rol desde Supabase
    role = get_supabase_role(request.user)
    print("🔥 Rol desde Supabase:", role)

    if role != "candidato":
        return JsonResponse({"error": "Solo los candidatos pueden postularse."}, status=403)

    # 2) Obtener la vacante
    vacante = get_object_or_404(Vacante, id=vacante_id)

    # 3) Validar estado activo y fecha
    ahora = timezone.now()
    fecha_exp = vacante.fecha_expiracion

    # Asegurar que la fecha sea aware
    if timezone.is_naive(fecha_exp):
        fecha_exp = timezone.make_aware(fecha_exp)

    if vacante.estado != "Publicado" or fecha_exp < ahora:
        return JsonResponse({"error": "La vacante no está activa."}, status=400)

    # 4) Validar si ya está postulado ANTES de procesar el archivo
    if Postulacion.objects.filter(candidato=request.user, vacante=vacante).exists():
        return JsonResponse({"error": "Ya se encuentra postulado a esta vacante."}, status=400)

    # 5) Obtener archivo enviado
    archivo_cv = request.FILES.get("cv")
    if not archivo_cv:
        return Response({"error": "Debe adjuntar un archivo 'cv'."}, status=400)

    # Validar tamaño del archivo (máximo 10MB para evitar timeouts)
    max_size = 10 * 1024 * 1024  # 10MB en bytes
    if archivo_cv.size > max_size:
        return JsonResponse({
            "error": f"El archivo es demasiado grande ({archivo_cv.size / 1024 / 1024:.1f}MB). Máximo permitido: 10MB"
        }, status=400)

    # Leer bytes del archivo
    contenido = archivo_cv.read()

    # 6) Subir archivo a Cloudinary
    try:
        logger.info(f"Iniciando subida de CV a Cloudinary: vacante={vacante_id} bytes={archivo_cv.size}")
        url_final = _upload_to_cloudinary(
            file_bytes=contenido,
            folder=f"postulaciones/vacantes/{vacante_id}",
            filename=f"cv_{request.user.id}_{archivo_cv.name}",
            resource_type="auto",
        )
        logger.info("CV subido exitosamente a Cloudinary")
            
    except Exception as e:
        logger.error(f"Excepción subiendo CV a Cloudinary: {str(e)}")
        return JsonResponse({"error": f"Error subiendo archivo: {str(e)}"}, status=500)

    cv_preview_url = None
    if str(archivo_cv.name).lower().endswith(".pdf"):
        try:
            upload_marker = "/upload/"
            suffix = url_final.split(upload_marker, 1)[1]
            parts = suffix.split("/")
            if parts and parts[0].startswith("v") and parts[0][1:].isdigit():
                parts = parts[1:]
            public_with_ext = "/".join(parts)
            public_id = public_with_ext.rsplit(".", 1)[0] if "." in public_with_ext else public_with_ext
            cv_preview_url, _ = cloudinary.utils.cloudinary_url(
                public_id,
                resource_type="image",
                type="upload",
                secure=True,
                format="jpg",
                page=1,
            )
        except Exception:
            cv_preview_url = None

    # 9) Crear postulación
    postulacion = Postulacion.objects.create(
        candidato=request.user,
        vacante=vacante,
        empresa=vacante.id_empresa,
        cv_url=url_final,
        estado="Postulado",
        fecha_postulacion=timezone.now()
    )

    # 10) Enviar correo de confirmacion
    try:
        candidato = postulacion.candidato
        empresa = postulacion.empresa
        vacante_obj = postulacion.vacante

        asunto = f"✅ Confirmación de Postulación - {vacante_obj.titulo} | {empresa.nombre}"

        mensaje = f"""Estimado/a {candidato.first_name or candidato.username},

¡Gracias por tu interés en formar parte de {empresa.nombre}!

Nos complace confirmar que hemos recibido exitosamente tu postulación para la posición de {vacante_obj.titulo}.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 DETALLES DE TU POSTULACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏢 Empresa: {empresa.nombre}
💼 Puesto: {vacante_obj.titulo}
📅 Fecha de postulación: {postulacion.fecha_postulacion.strftime('%d/%m/%Y a las %H:%M')}
📍 Ubicación: {vacante_obj.ubicacion or 'Por definir'}
🏠 Modalidad: {vacante_obj.modalidad_trabajo or 'Por definir'}
📊 Estado actual: POSTULADO ✓
🆔 ID de Postulación: #{postulacion.id}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 PRÓXIMOS PASOS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1️⃣ Revisión inicial (3-7 días hábiles)
2️⃣ Evaluación del perfil
3️⃣ Contacto directo si avanzas en el proceso

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Este es un mensaje automático. Por favor, no responder directamente.

Atentamente,
Equipo de Gestión de Talento Humano  
{empresa.nombre}

Sistema de Gestión de Candidatos | TalentoHub
Correo generado el {timezone.now().strftime('%d/%m/%Y a las %H:%M')}
"""

        sent = send_plain_email(
            subject=asunto,
            message=mensaje,
            recipient_list=[candidato.email],
            fail_silently=True,
        )

        if sent:
            logger.info(f"✅ Correo enviado exitosamente a {candidato.email}")
            comentario = f"\n[{timezone.now().isoformat()}] Correo de confirmación enviado a {candidato.email}"
            postulacion.comentarios = (postulacion.comentarios or "") + comentario
            postulacion.save(update_fields=["comentarios"])
        else:
            logger.warning(f"⚠️ No se pudo enviar correo de confirmación a {candidato.email}")

    except Exception as e:
        logger.error(f"❌ Error enviando correo de confirmación: {e}")

    return Response(
    {
        "message": "Postulación realizada con éxito.",
        "cv_url": url_final,
        "cv_preview_url": cv_preview_url,
        "estado": "Postulado",
        "email": "Correo enviado" if 'sent' in locals() and sent else "Falla en envío de correo"
    },
    status=201
)


from rest_framework_simplejwt.authentication import JWTAuthentication

@api_view(["GET"])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
def listar_postulaciones_por_vacante(request, id_vacante):

    # Obtener rol e id_empresa normalizados para soportar variantes (rrhh/empleado_rrhh).
    role = normalize_role(getattr(request.user, "role", None) or get_supabase_role(request.user))
    id_empresa_usuario = get_supabase_empresa_id(request.user)
    try:
        id_empresa_usuario = int(id_empresa_usuario) if id_empresa_usuario is not None else None
    except Exception:
        id_empresa_usuario = None

    print("🔥 Rol del usuario:", role)
    print("🏭 Empresa del usuario:", id_empresa_usuario)

    vacante = get_object_or_404(Vacante, id=id_vacante)
    vacante_empresa_id = getattr(vacante, "id_empresa_id", None)

    if role not in [Roles.EMPLEADO_RRHH, Roles.ADMIN]:
        return Response({"detail": "No autorizado"}, status=403)

    if role == Roles.EMPLEADO_RRHH and id_empresa_usuario != vacante_empresa_id:
        return Response({"detail": "No pertenece a tu empresa"}, status=403)

    postulaciones = Postulacion.objects.filter(vacante_id=id_vacante)
    serializer = PostulacionSerializer(postulaciones, many=True)

    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def metrics_dashboard(request):
    """Devuelve métricas agregadas por vacante. Público.

    Filtros por query params:
    - from: ISO date (yyyy-mm-dd) fecha mínima de postulacion
    - to: ISO date fecha máxima
    - area: cadena que filtra `Vacante.ubicacion` (icontains)
    """
    fecha_from = request.GET.get('from')
    fecha_to = request.GET.get('to')
    area = request.GET.get('area')
    # Aceptar vacante_id o id_vacante como query param (por compatibilidad con Postman screenshots)
    vacante_param = request.GET.get('vacante_id') or request.GET.get('id_vacante')

    vacantes_qs = Vacante.objects.all()
    if vacante_param:
        try:
            vac_id = int(vacante_param)
            vacantes_qs = vacantes_qs.filter(id=vac_id)
        except Exception:
            pass
    if area:
        vacantes_qs = vacantes_qs.filter(ubicacion__icontains=area)

    out = []
    for v in vacantes_qs:
        postulaciones = Postulacion.objects.filter(vacante=v)
        if fecha_from:
            try:
                postulaciones = postulaciones.filter(fecha_postulacion__gte=fecha_from)
            except Exception:
                pass
        if fecha_to:
            try:
                postulaciones = postulaciones.filter(fecha_postulacion__lte=fecha_to)
            except Exception:
                pass

        total = postulaciones.count()
        por_estado = {row['estado']: row['count'] for row in postulaciones.values('estado').annotate(count=Count('id'))}
        ultima = postulaciones.aggregate(last=Max('fecha_postulacion')).get('last')

        out.append({
            'vacante_id': v.id,
            'titulo': v.titulo,
            'empresa_id': v.id_empresa_id,
            'empresa_nombre': v.id_empresa.nombre if v.id_empresa else None,
            'total_postulaciones': total,
            'postulaciones_por_estado': por_estado,
            'ultima_postulacion': ultima,
        })

    return Response({'vacantes': out})


@api_view(['GET'])
@permission_classes([permissions.AllowAny])
def export_metrics_vacante(request, vacante_id, fmt):
    """Exporta métricas para una vacante dada usando ruta limpia.

    URL: /api/metrics/vacante/<vacante_id>/export/<fmt>/
    fmt: 'csv' | 'excel' | 'pdf'
    Público - no requiere autenticación.
    """
    fmt = (fmt or '').lower()
    if fmt not in ('csv', 'excel', 'pdf'):
        return Response({'error': "Formato inválido. Use 'csv' o 'pdf'."}, status=400)

    fecha_from = request.GET.get('from')
    fecha_to = request.GET.get('to')
    area = request.GET.get('area')

    try:
        vacante = Vacante.objects.get(id=vacante_id)
    except Vacante.DoesNotExist:
        return Response({'error': 'Vacante no encontrada'}, status=404)

    vacantes_qs = Vacante.objects.filter(id=vacante_id)

    rows = []
    header = ['vacante_id', 'titulo', 'empresa_id', 'empresa_nombre', 'total_postulaciones', 'ultima_postulacion', 'estado', 'estado_count']

    for v in vacantes_qs:
        postulaciones = Postulacion.objects.filter(vacante=v)
        if fecha_from:
            postulaciones = postulaciones.filter(fecha_postulacion__gte=fecha_from)
        if fecha_to:
            postulaciones = postulaciones.filter(fecha_postulacion__lte=fecha_to)

        total = postulaciones.count()
        ultima = postulaciones.aggregate(last=Max('fecha_postulacion')).get('last')
        estados = postulaciones.values('estado').annotate(count=Count('id'))
        if not estados:
            rows.append([v.id, v.titulo, v.id_empresa_id, getattr(v.id_empresa, 'nombre', None), total, ultima, None, 0])
        else:
            for s in estados:
                rows.append([v.id, v.titulo, v.id_empresa_id, getattr(v.id_empresa, 'nombre', None), total, ultima, s['estado'], s['count']])

    # CSV/Excel
    if fmt in ('excel', 'csv'):
        sio = io.StringIO()
        writer = csv.writer(sio)
        writer.writerow(header)
        for r in rows:
            writer.writerow([str(c) if c is not None else '' for c in r])
        content = sio.getvalue()
        filename = f"metrics_vacante_{vacante_id}.csv"
        resp = HttpResponse(content, content_type='text/csv')
        resp['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp

    # PDF usando matplotlib para un gráfico más bonito y opcional logo de empresa
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from reportlab.lib.pagesizes import letter
        from reportlab.pdfgen import canvas
        from reportlab.lib.units import inch
        from reportlab.lib.utils import ImageReader
        import urllib.request
        from PIL import Image
    except Exception:
        return Response({'error': "Para exportar PDF instale 'matplotlib' y 'reportlab' (pip install matplotlib reportlab pillow)."}, status=400)

    # Preparar datos
    v = vacante
    postulaciones = Postulacion.objects.filter(vacante=v)
    if fecha_from:
        postulaciones = postulaciones.filter(fecha_postulacion__gte=fecha_from)
    if fecha_to:
        postulaciones = postulaciones.filter(fecha_postulacion__lte=fecha_to)

    total = postulaciones.count()
    estados_q = list(postulaciones.values('estado').annotate(count=Count('id')).order_by('-count'))
    estados = [e['estado'] for e in estados_q] if estados_q else []
    counts = [e['count'] for e in estados_q] if estados_q else []

    # Generar gráfico con matplotlib
    fig = plt.figure(figsize=(7.5, 4))
    ax = fig.add_subplot(111)
    if counts:
        bars = ax.bar(range(len(counts)), counts, color='#e74c3c')
        ax.set_xticks(range(len(counts)))
        ax.set_xticklabels(estados, rotation=30, ha='right')
        ax.set_ylabel('Cantidad')
        ax.set_title(f'Postulaciones por estado - Vacante {v.id}')
        # Anotar valores encima de barras
        for bar in bars:
            hgt = bar.get_height()
            ax.annotate(f'{int(hgt)}', xy=(bar.get_x() + bar.get_width() / 2, hgt), xytext=(0, 4),
                        textcoords='offset points', ha='center', va='bottom', fontsize=9)
    else:
        ax.text(0.5, 0.5, 'No hay postulaciones', ha='center', va='center')
        ax.set_xticks([])
        ax.set_yticks([])

    fig.tight_layout()
    img_buf = BytesIO()
    fig.savefig(img_buf, format='png', dpi=150, bbox_inches='tight')
    plt.close(fig)
    img_buf.seek(0)

    # Construir PDF e insertar imagen
    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)
    w, h = letter

    # Header: título y metadata
    c.setFont('Helvetica-Bold', 16)
    c.drawString(40, h - 40, f"Reporte de métricas - Vacante {v.id}: {v.titulo}")
    c.setFont('Helvetica', 9)
    empresa_nombre = getattr(v.id_empresa, 'nombre', None) if getattr(v, 'id_empresa', None) else ''
    c.drawString(40, h - 60, f"Empresa: {empresa_nombre}    Vacante ID: {v.id}")
    ultima = postulaciones.aggregate(last=Max('fecha_postulacion')).get('last')
    c.drawString(40, h - 75, f"Total postulaciones: {total}    Última postulación: {ultima}")

    # Insertar logo si existe
    logo_y = h - 40
    logo_size = 60
    logo_url = getattr(v.id_empresa, 'logo_url', None) if getattr(v, 'id_empresa', None) else None
    if logo_url:
        try:
            with urllib.request.urlopen(logo_url, timeout=5) as resp:
                logo_bytes = resp.read()
            logo_img = Image.open(BytesIO(logo_bytes))
            logo_img_reader = ImageReader(BytesIO(logo_bytes))
            c.drawImage(logo_img_reader, w - 40 - logo_size, h - 40 - (logo_size/2), width=logo_size, height=logo_size, preserveAspectRatio=True, mask='auto')
        except Exception:
            # si falla el logo, no interrumpe la generación
            logger.warning('No se pudo descargar/incluir el logo de la empresa: %s', logo_url)

    # Dibujar el gráfico PNG debajo del header
    img_reader = ImageReader(img_buf)
    img_w = w - 80
    img_h = 3.5 * inch
    c.drawImage(img_reader, 40, h - 120 - img_h, width=img_w, height=img_h, preserveAspectRatio=True, mask='auto')

    # Añadir tabla simple de estados y conteos
    text_y = h - 120 - img_h - 20
    c.setFont('Helvetica-Bold', 11)
    c.drawString(40, text_y, 'Detalle por estado:')
    c.setFont('Helvetica', 10)
    ty = text_y - 14
    if estados_q:
        for e in estados_q:
            c.drawString(48, ty, f"- {e['estado']}: {e['count']}")
            ty -= 12
    else:
        c.drawString(48, ty, 'No hay estados para mostrar')

    # Footer: fecha de generación
    c.setFont('Helvetica-Oblique', 8)
    c.drawString(40, 20, f"Generado: {timezone.now().isoformat()}")

    c.showPage()
    c.save()
    buffer.seek(0)
    filename = f"metrics_vacante_{vacante_id}.pdf"
    return HttpResponse(buffer.getvalue(), content_type='application/pdf', headers={
        'Content-Disposition': f'attachment; filename="{filename}"'
    })


@api_view(['GET'])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
def export_metrics(request):
    """Exporta métricas (CSV o PDF) para una o varias vacantes.

    Query params:
    - format: 'excel'|'csv'|'pdf' (por defecto 'excel' -> CSV)
    - vacante_id: opcional; si viene, exporta solo esa vacante
    - from, to, area: mismos filtros que `metrics_dashboard`
    """
    caller_role = normalize_role(getattr(request.user, 'role', None) or get_supabase_role(request.user))
    if caller_role != Roles.ADMIN:
        return Response({'error': 'No autorizado'}, status=403)

    # No asumir 'excel' por defecto: requerimos que el cliente especifique el formato.
    fmt_raw = request.GET.get('format')
    logger.debug("Export metrics called with query params: %s", dict(request.GET))
    if not fmt_raw:
        return Response({'error': "Debe indicar el query param 'format' (csv|excel|pdf)."}, status=400)
    fmt = fmt_raw.lower()
    # Aceptar ambos nombres para vacante en querystring
    vacante_id = request.GET.get('vacante_id') or request.GET.get('id_vacante')

    # Reusar lógica de metrics_dashboard simplificada
    fecha_from = request.GET.get('from')
    fecha_to = request.GET.get('to')
    area = request.GET.get('area')

    vacantes_qs = Vacante.objects.all()
    if vacante_id:
        try:
            vacantes_qs = vacantes_qs.filter(id=int(vacante_id))
        except Exception:
            pass
    if area:
        vacantes_qs = vacantes_qs.filter(ubicacion__icontains=area)

    rows = []
    header = ['vacante_id', 'titulo', 'empresa_id', 'empresa_nombre', 'total_postulaciones', 'ultima_postulacion', 'estado', 'estado_count']

    for v in vacantes_qs:
        postulaciones = Postulacion.objects.filter(vacante=v)
        if fecha_from:
            postulaciones = postulaciones.filter(fecha_postulacion__gte=fecha_from)
        if fecha_to:
            postulaciones = postulaciones.filter(fecha_postulacion__lte=fecha_to)

        total = postulaciones.count()
        ultima = postulaciones.aggregate(last=Max('fecha_postulacion')).get('last')
        estados = postulaciones.values('estado').annotate(count=Count('id'))
        if not estados:
            rows.append([v.id, v.titulo, v.id_empresa_id, getattr(v.id_empresa, 'nombre', None), total, ultima, None, 0])
        else:
            for s in estados:
                rows.append([v.id, v.titulo, v.id_empresa_id, getattr(v.id_empresa, 'nombre', None), total, ultima, s['estado'], s['count']])

    # CSV/Excel (CSV compatible con Excel)
    if fmt in ('excel', 'csv'):
        sio = io.StringIO()
        writer = csv.writer(sio)
        writer.writerow(header)
        for r in rows:
            writer.writerow([str(c) if c is not None else '' for c in r])
        content = sio.getvalue()
        filename = f"metrics_{vacante_id or 'all'}.csv"
        resp = HttpResponse(content, content_type='text/csv')
        resp['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp

    # PDF (intento con reportlab si está instalado)
    if fmt == 'pdf':
        try:
            from reportlab.lib.pagesizes import letter
            from reportlab.pdfgen import canvas
            from reportlab.lib import colors
            from reportlab.lib.units import inch
            from reportlab.graphics.shapes import Drawing, String
            from reportlab.graphics.charts.barcharts import VerticalBarChart
            from reportlab.graphics import renderPDF
        except Exception:
            return Response({'error': "Para exportar PDF instale 'reportlab' (pip install reportlab) o use format=csv."}, status=400)

        buffer = BytesIO()
        c = canvas.Canvas(buffer, pagesize=letter)
        w, h = letter

        # Organizar los datos por vacante y generar una página por vacante
        for v in vacantes_qs:
            # Cabecera
            c.setFont('Helvetica-Bold', 14)
            c.drawString(40, h - 40, f"Reporte de métricas - Vacante {v.id}: {v.titulo}")

            # Subtítulo empresa y fecha
            c.setFont('Helvetica', 9)
            empresa_nombre = getattr(v.id_empresa, 'nombre', None) if getattr(v, 'id_empresa', None) else ''
            c.drawString(40, h - 60, f"Empresa: {empresa_nombre}    Vacante ID: {v.id}")

            # Recalcular postulaciones y estados para esta vacante
            postulaciones = Postulacion.objects.filter(vacante=v)
            if fecha_from:
                postulaciones = postulaciones.filter(fecha_postulacion__gte=fecha_from)
            if fecha_to:
                postulaciones = postulaciones.filter(fecha_postulacion__lte=fecha_to)

            total = postulaciones.count()
            estados_q = list(postulaciones.values('estado').annotate(count=Count('id')).order_by('-count'))

            # Texto resumen
            c.setFont('Helvetica', 10)
            c.drawString(40, h - 90, f"Total postulaciones: {total}")
            ultima = postulaciones.aggregate(last=Max('fecha_postulacion')).get('last')
            c.drawString(200, h - 90, f"Última postulación: {ultima}")

            # Preparar datos para gráfico
            estados = [e['estado'] for e in estados_q]
            counts = [e['count'] for e in estados_q]

            if total > 0 and counts:
                # Dibujar gráfico de barras usando Graphics
                drawing_width = 6.5 * inch
                drawing_height = 3 * inch
                drawing = Drawing(drawing_width, drawing_height)

                bc = VerticalBarChart()
                bc.x = 50
                bc.y = 20
                bc.height = drawing_height - 60
                bc.width = drawing_width - 120
                bc.data = [counts]
                bc.strokeColor = colors.black
                bc.valueAxis.labels.fontSize = 8
                bc.categoryAxis.labels.boxAnchor = 'ne'
                bc.categoryAxis.labels.dy = -2
                bc.categoryAxis.labels.angle = 30
                bc.categoryAxis.categoryNames = estados
                bc.bars.fillColor = colors.HexColor('#4f81bd')

                drawing.add(bc)

                # Leyenda con porcentajes
                start_y = h - 140
                c.setFont('Helvetica-Bold', 10)
                c.drawString(40, start_y, 'Postulaciones por estado (cantidad y porcentaje):')
                c.setFont('Helvetica', 9)
                y_text = start_y - 14
                for est, cnt in zip(estados, counts):
                    pct = (cnt / total) * 100 if total else 0
                    c.drawString(48, y_text, f"- {est}: {cnt} ({pct:.1f}%)")
                    y_text -= 12

                # Renderizar el drawing en el canvas
                renderPDF.draw(drawing, c, 40, h - 420)
            else:
                c.setFont('Helvetica-Oblique', 9)
                c.drawString(40, h - 140, 'No hay postulaciones para esta vacante en el rango solicitado.')

            c.showPage()

        c.save()
        buffer.seek(0)
        filename = f"metrics_{vacante_id or 'all'}.pdf"
        return HttpResponse(buffer.getvalue(), content_type='application/pdf', headers={
            'Content-Disposition': f'attachment; filename="{filename}"'
        })

    return Response({'error': 'Formato no soportado. Use format=csv|excel|pdf'}, status=400)
# ----------------------------
# Gestion de postulaciones
# ----------------------------
@api_view(['PATCH'])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
def actualizar_estado_postulacion(request, postulacion_id):
    role_raw = getattr(request.user, 'role', None) or get_supabase_role(request.user)
    role = normalize_role(role_raw)

    if role not in ["admin", "empleado_rrhh"]:
        return Response({"error": "No autorizado"}, status=403)

    postulacion = get_object_or_404(
        Postulacion.objects.select_related("vacante"),
        id=postulacion_id
    )

    # Verificar que el RRHH esté asignado a esa vacante
    if role == "empleado_rrhh":
        asignado = VacanteRRHH.objects.filter(
            vacante=postulacion.vacante,
            rrhh_user=request.user
        ).exists()
        if not asignado:
            return Response(
                {"error": "No puedes modificar postulaciones de vacantes que no gestionas."},
                status=403
            )

    nuevo_estado = request.data.get("estado")
    if not nuevo_estado:
        return Response({"error": "Debes enviar el campo 'estado'."}, status=400)

    ESTADOS_VALIDOS = ["Postulado", "En revisión", "Entrevista", "Rechazado", "Proceso de contratacion", "Contratado"]
    if nuevo_estado not in ESTADOS_VALIDOS:
        return Response({
            "error": f"Estado inválido. Usa uno de: {', '.join(ESTADOS_VALIDOS)}"
        }, status=400)

    estado_anterior = postulacion.estado
    postulacion.estado = nuevo_estado
    postulacion.save(update_fields=["estado"])

    # Enviar correo según el nuevo estado (SÍNCRONO para garantizar envío en producción)
    if nuevo_estado != estado_anterior:
        # Registrar cambio primero
        comentario_cambio = f"\n[{timezone.now().isoformat()}] Estado cambiado: '{estado_anterior}' → '{nuevo_estado}' por {request.user.email}"
        postulacion.comentarios = (postulacion.comentarios or "") + comentario_cambio
        postulacion.save(update_fields=["comentarios"])
        
        try:
            candidato = postulacion.candidato
            vacante_obj = postulacion.vacante
            empresa = postulacion.empresa

            print(f"📧 Preparando correo SMTP para estado '{nuevo_estado}' → {candidato.email}")
            logger.info(f"📧 Preparando correo SMTP para estado '{nuevo_estado}' → {candidato.email}")
            # Plantillas de correo según estado
            templates = {
                "Postulado": {
                    "asunto": f"✅ Confirmación de postulación - {vacante_obj.titulo} | {empresa.nombre}",
                    "mensaje": f"""Estimado/a {candidato.first_name or candidato.username},

Hemos registrado correctamente tu postulación.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 RESUMEN DE TU POSTULACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏢 Empresa: {empresa.nombre}
💼 Vacante: {vacante_obj.titulo}
🔄 Estado actual: POSTULADO ✅
📅 Fecha de actualización: {timezone.now().strftime('%d/%m/%Y a las %H:%M')}
🆔 ID de Postulación: #{postulacion.id}

Gracias por confiar en Talento Hub. Te notificaremos cuando haya avances en tu proceso.

Atentamente,
Equipo de Gestión de Talento Humano
{empresa.nombre}
"""
                },
                "En revisión": {
                    "asunto": f"🔍 Tu postulación está en revisión - {vacante_obj.titulo} | {empresa.nombre}",
                    "mensaje": f"""Estimado/a {candidato.first_name or candidato.username},

¡Buenas noticias! Tu postulación ha avanzado a la siguiente etapa.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 ACTUALIZACIÓN DE ESTADO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏢 Empresa: {empresa.nombre}
💼 Puesto: {vacante_obj.titulo}
📍 Ubicación: {vacante_obj.ubicacion or 'Por definir'}
🔄 Estado actual: EN REVISIÓN 🔍
📅 Fecha de actualización: {timezone.now().strftime('%d/%m/%Y a las %H:%M')}
🆔 ID de Postulación: #{postulacion.id}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 ¿QUÉ SIGNIFICA ESTO?
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Tu perfil profesional está siendo evaluado detalladamente por nuestro equipo de Recursos Humanos.

Estamos revisando:
✓ Tu experiencia laboral y trayectoria profesional
✓ Tus habilidades técnicas y competencias
✓ Tu formación académica y certificaciones
✓ La compatibilidad de tu perfil con los requisitos del puesto
✓ Referencias y recomendaciones (si aplica)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏰ TIEMPOS ESTIMADOS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📆 Duración de revisión: 3 a 5 días hábiles
🔔 Próxima comunicación: Si tu perfil es seleccionado, te contactaremos directamente

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 MIENTRAS ESPERAS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📱 Mantén activos tus medios de contacto (teléfono y correo)
📧 Revisa tu bandeja de entrada y spam regularmente
📄 Ten lista tu documentación actualizada
🏢 Investiga más sobre {empresa.nombre}, su misión, visión y valores
💪 Prepárate mentalmente para posibles entrevistas

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Agradecemos tu paciencia durante este proceso. Te mantendremos informado/a sobre cualquier avance.

¡Mucho éxito!

Atentamente,

Equipo de Gestión de Talento Humano
{empresa.nombre}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sistema de Gestión de Candidatos | TalentoHub
Correo generado automáticamente el {timezone.now().strftime('%d/%m/%Y a las %H:%M')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
                },
                "Entrevista": {
                    "asunto": f"🎉 ¡Felicitaciones! Has sido seleccionado para entrevista - {vacante_obj.titulo}",
                    "mensaje": f"""Estimado/a {candidato.first_name or candidato.username},

¡EXCELENTES NOTICIAS! 🎊

Tu perfil ha destacado entre los candidatos y hemos decidido continuar con tu proceso de selección.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 ACTUALIZACIÓN DE ESTADO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏢 Empresa: {empresa.nombre}
💼 Puesto: {vacante_obj.titulo}
📍 Ubicación: {vacante_obj.ubicacion or 'Por definir'}
🏠 Modalidad: {vacante_obj.modalidad_trabajo or 'Por definir'}
🔄 Estado actual: SELECCIONADO PARA ENTREVISTA ⭐
📅 Fecha de actualización: {timezone.now().strftime('%d/%m/%Y a las %H:%M')}
🆔 ID de Postulación: #{postulacion.id}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📞 PRÓXIMOS PASOS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⏰ CONTACTO INMEDIATO
Nuestro equipo de Recursos Humanos se comunicará contigo en las próximas 24-48 horas para:

✓ Confirmar tu interés y disponibilidad
✓ Coordinar fecha y hora de la entrevista
✓ Definir modalidad (presencial, virtual o telefónica)
✓ Proporcionar detalles sobre el proceso
✓ Indicar duración estimada de la entrevista
✓ Presentar a las personas que te entrevistarán

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 PREPÁRATE PARA LA ENTREVISTA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏢 INVESTIGA LA EMPRESA
• Conoce la historia, misión y visión de {empresa.nombre}
• Revisa sus productos/servicios principales
• Identifica sus valores corporativos y cultura organizacional
• Consulta sus redes sociales y sitio web oficial

💼 PREPARA TU PRESENTACIÓN
• Repasa tu experiencia laboral más relevante
• Identifica 3-5 logros profesionales clave
• Prepara ejemplos concretos de situaciones laborales (método STAR)
• Ten claro por qué quieres trabajar en {empresa.nombre}

❓ PREPARA PREGUNTAS INTELIGENTES
• Sobre el puesto y sus responsabilidades
• Sobre el equipo de trabajo y la cultura
• Sobre oportunidades de crecimiento profesional
• Sobre los retos del puesto

📄 DOCUMENTACIÓN REQUERIDA
• Copia impresa o digital de tu CV actualizado
• Portafolio de proyectos (si aplica para el puesto)
• Certificados de estudios y capacitaciones
• Referencias laborales disponibles

💻 SI ES ENTREVISTA VIRTUAL
• Verifica tu conexión a internet
• Prueba tu cámara y micrófono
• Busca un lugar tranquilo e iluminado
• Ten instalado Zoom/Teams/Google Meet
• Viste de manera profesional (incluso si es virtual)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 CONSEJOS CLAVE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ Sé puntual (llega 10-15 minutos antes)
✓ Mantén contacto visual y lenguaje corporal positivo
✓ Responde con sinceridad y seguridad
✓ Escucha activamente las preguntas
✓ Sé tú mismo/a y muestra tu entusiasmo
✓ Apaga tu teléfono o ponlo en silencio

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Estamos emocionados de conocerte mejor y explorar cómo puedes contribuir a {empresa.nombre}.

¡Te deseamos mucho éxito en tu entrevista!

Atentamente,

Equipo de Gestión de Talento Humano
{empresa.nombre}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sistema de Gestión de Candidatos | TalentoHub
Correo generado automáticamente el {timezone.now().strftime('%d/%m/%Y a las %H:%M')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
                },
                "Proceso de contratacion": {
                    "asunto": f"🎊 ¡FELICITACIONES! Iniciamos tu proceso de contratación - {vacante_obj.titulo}",
                    "mensaje": f"""Estimado/a {candidato.first_name or candidato.username},

¡EXCELENTES NOTICIAS! 🎉🎉🎉

Después de un riguroso proceso de selección, nos complace informarte que HAS SIDO SELECCIONADO/A para formar parte de nuestro equipo.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌟 ACTUALIZACIÓN DE ESTADO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏢 Empresa: {empresa.nombre}
💼 Puesto: {vacante_obj.titulo}
📍 Ubicación: {vacante_obj.ubicacion or 'Por definir'}
🏠 Modalidad: {vacante_obj.modalidad_trabajo or 'Por definir'}
⏰ Jornada: {vacante_obj.tipo_jornada or 'Por definir'}
💰 Salario: {vacante_obj.salario if vacante_obj.salario else 'Según lo acordado en entrevista'}
🔄 Estado actual: PROCESO DE CONTRATACIÓN 📋✅
📅 Fecha de selección: {timezone.now().strftime('%d/%m/%Y a las %H:%M')}
🆔 ID de Postulación: #{postulacion.id}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 DOCUMENTACIÓN REQUERIDA (URGENTE)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Por favor, reúne y prepara los siguientes documentos ORIGINALES y COPIAS:

📄 IDENTIFICACIÓN PERSONAL
✓ Documento de identidad vigente (DPI/Cédula/Pasaporte)
✓ Partida de nacimiento certificada (si aplica)
✓ 2 fotografías tamaño cédula recientes a color

👨‍🎓 FORMACIÓN ACADÉMICA
✓ Títulos universitarios certificados
✓ Diplomas de estudios superiores
✓ Certificados de capacitaciones y cursos
✓ Constancias de idiomas (si aplica)

💼 EXPERIENCIA LABORAL
✓ Cartas de recomendación laboral (mínimo 2)
✓ Certificados de trabajo de empleos anteriores
✓ Hoja de vida actualizada y detallada

🏥 DOCUMENTOS MÉDICOS Y LEGALES
✓ Certificado médico de buena salud (reciente)
✓ Antecedentes penales actualizados
✓ Antecedentes policiacos
✓ Constancia de afiliación al seguro social (si aplica)

🏦 INFORMACIÓN BANCARIA
✓ Estado de cuenta bancaria reciente
✓ Número de cuenta para depósitos (si aplica)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📝 PASOS A SEGUIR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PASO 1️⃣: REVISIÓN Y FIRMA DE CONTRATO (Próximos 3-5 días)
• Recibirás tu contrato de trabajo para revisión
• Lee cuidadosamente todos los términos y condiciones
• Consulta cualquier duda antes de firmar
• Firma y devuelve el contrato en los plazos indicados

PASO 2️⃣: ENTREGA DE DOCUMENTACIÓN (Plazo: 5 días hábiles)
• Entrega toda la documentación requerida completa
• Asegúrate de que todas las copias sean legibles
• Organiza los documentos según la lista proporcionada

PASO 3️⃣: PROCESO DE ONBOARDING
• Completarás formularios administrativos internos
• Recibirás información sobre políticas de la empresa
• Conocerás los beneficios y prestaciones

PASO 4️⃣: INDUCCIÓN CORPORATIVA (Fecha por confirmar)
• Programa de bienvenida e integración
• Capacitación sobre sistemas y procesos
• Presentación del equipo de trabajo
• Recorrido por las instalaciones

PASO 5️⃣: INICIO DE LABORES
• Confirmaremos tu fecha de inicio oficial
• Recibirás tu equipo de trabajo y credenciales
• Comenzarás tu plan de entrenamiento específico

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⏰ PLAZOS IMPORTANTES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🚨 CRÍTICO: Debes entregar toda la documentación dentro de los próximos 5 DÍAS HÁBILES para no retrasar tu proceso de incorporación.

Si tienes dificultades para conseguir algún documento, comunícate inmediatamente con RRHH.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📞 CONTACTO Y SEGUIMIENTO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Para cualquier consulta, duda o información adicional:

📧 Responde a este correo electrónico
📱 Contacta al Departamento de Recursos Humanos de {empresa.nombre}
⏰ Horario de atención: Lunes a Viernes, 8:00 AM - 5:00 PM

Nuestro equipo está disponible para apoyarte en todo el proceso.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

¡Bienvenido/a a la familia {empresa.nombre}!

Estamos emocionados de que comiences esta nueva etapa profesional con nosotros. Tu talento, experiencia y dedicación serán fundamentales para alcanzar nuestros objetivos.

Confiamos en que esta será una relación laboral exitosa y mutuamente beneficiosa.

¡Nos vemos pronto!

Atentamente,

Equipo de Gestión de Talento Humano
{empresa.nombre}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sistema de Gestión de Candidatos | TalentoHub
Correo generado automáticamente el {timezone.now().strftime('%d/%m/%Y a las %H:%M')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
                },
                "Contratado": {
                    "asunto": f"🎉 ¡BIENVENIDO/A AL EQUIPO! Tu contratación está completa - {empresa.nombre}",
                    "mensaje": f"""Estimado/a {candidato.first_name or candidato.username},

🎊 ¡FELICITACIONES! 🎊

Tu proceso de contratación ha sido completado exitosamente. Oficialmente eres parte del equipo de {empresa.nombre}.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🌟 CONFIRMACIÓN DE CONTRATACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🎉 BIENVENIDO/A A {empresa.nombre.upper()} 🎉

🏢 Empresa: {empresa.nombre}
💼 Tu puesto: {vacante_obj.titulo}
📍 Ubicación: {vacante_obj.ubicacion or 'Por definir'}
🏠 Modalidad: {vacante_obj.modalidad_trabajo or 'Por definir'}
⏰ Jornada laboral: {vacante_obj.tipo_jornada or 'Por definir'}
🔄 Estado: CONTRATADO ✅
📅 Fecha de contratación: {timezone.now().strftime('%d/%m/%Y a las %H:%M')}
🆔 ID de Empleado: Por asignar por RRHH

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📅 INICIO DE LABORES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Nuestro equipo de Recursos Humanos se comunicará contigo en las PRÓXIMAS HORAS para:

✓ Confirmar tu fecha exacta de inicio
✓ Coordinar tu sesión de inducción corporativa
✓ Entregarte credenciales y accesos a sistemas
✓ Asignarte tu equipo de trabajo (computadora, teléfono, etc.)
✓ Presentarte oficialmente a tu equipo de trabajo
✓ Programar tu recorrido por las instalaciones
✓ Entregarte tu contrato firmado y documentación oficial

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📋 TU PRIMER DÍA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PROGRAMA DE INDUCCIÓN INTEGRAL:

🏢 BIENVENIDA CORPORATIVA (9:00 AM)
• Recepción oficial por parte del equipo de RRHH
• Presentación de la empresa, historia y valores
• Entrega de kit de bienvenida
• Firma de documentos finales

👥 INTEGRACIÓN AL EQUIPO (10:30 AM)
• Presentación con tu jefe inmediato
• Conoce a tus compañeros de equipo
• Tour por tu área de trabajo
• Asignación de tu espacio laboral

💻 CONFIGURACIÓN TECNOLÓGICA (12:00 PM)
• Entrega de equipo de cómputo y herramientas
• Creación de cuentas y credenciales
• Capacitación en sistemas internos
• Acceso a plataformas corporativas

🎓 CAPACITACIÓN INICIAL (2:00 PM)
• Políticas y procedimientos internos
• Normas de seguridad y salud ocupacional
• Beneficios y prestaciones de ley
• Código de conducta y ética profesional

📍 RECORRIDO GENERAL (4:00 PM)
• Conoce todas las instalaciones
• Ubicación de áreas importantes
• Presentación con otros departamentos
• Información sobre servicios disponibles

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💼 DOCUMENTACIÓN IMPORTANTE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Asegúrate de tener lista y COMPLETA la siguiente documentación para tu primer día:

✓ Documento de identidad original
✓ Fotos tamaño cédula (2 adicionales)
✓ Comprobante de domicilio reciente
✓ Documentación académica certificada
✓ Certificado médico de buena salud
✓ Referencias laborales originales
✓ Cualquier otro documento pendiente

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🎯 EXPECTATIVAS Y OBJETIVOS
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Durante tus primeras semanas en {empresa.nombre}:

SEMANA 1-2: ADAPTACIÓN
• Conocer procesos y metodologías de trabajo
• Familiarizarte con herramientas y sistemas
• Establecer relaciones con tu equipo
• Comprender tu rol y responsabilidades

SEMANA 3-4: INTEGRACIÓN
• Participar activamente en proyectos
• Aplicar conocimientos adquiridos
• Comenzar a generar resultados
• Recibir retroalimentación constante

MES 2-3: PRODUCTIVIDAD
• Trabajar de manera autónoma
• Contribuir significativamente al equipo
• Proponer mejoras e innovaciones
• Alcanzar objetivos establecidos

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 CONSEJOS PARA TU ÉXITO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

✓ Sé puntual desde el primer día
✓ Mantén una actitud positiva y proactiva
✓ Haz preguntas cuando tengas dudas
✓ Toma notas durante las capacitaciones
✓ Conoce y respeta la cultura organizacional
✓ Sé amable y respetuoso con todos
✓ Demuestra tu compromiso y profesionalismo
✓ Aprende continuamente y adapta-te rápido

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📞 CONTACTO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Para cualquier consulta antes de tu inicio:

📧 Responde a este correo
📱 Contacta a Recursos Humanos
⏰ Disponibilidad: Lunes a Viernes, 8:00 AM - 5:00 PM

Estamos aquí para apoyarte en tu integración.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{candidato.first_name}, estamos verdaderamente emocionados de tenerte en nuestro equipo. Tu experiencia, habilidades y talento serán un gran aporte para {empresa.nombre}.

Confiamos en que esta será una relación laboral exitosa, productiva y llena de crecimiento profesional.

¡Bienvenido/a a la familia {empresa.nombre}!

¡Nos vemos muy pronto!

Con entusiasmo,

Equipo de Gestión de Talento Humano
{empresa.nombre}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sistema de Gestión de Candidatos | TalentoHub
Correo generado automáticamente el {timezone.now().strftime('%d/%m/%Y a las %H:%M')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
                },
                "Rechazado": {
                    "asunto": f"Actualización sobre tu postulación - {vacante_obj.titulo} | {empresa.nombre}",
                    "mensaje": f"""Estimado/a {candidato.first_name or candidato.username},

Esperamos que te encuentres muy bien.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 ACTUALIZACIÓN DE TU POSTULACIÓN
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏢 Empresa: {empresa.nombre}
💼 Puesto aplicado: {vacante_obj.titulo}
📅 Fecha de postulación: {postulacion.fecha_postulacion.strftime('%d/%m/%Y')}
📅 Fecha de esta actualización: {timezone.now().strftime('%d/%m/%Y a las %H:%M')}
🆔 ID de Postulación: #{postulacion.id}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💬 RESULTADO DEL PROCESO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Queremos agradecerte sinceramente por tu interés en formar parte de {empresa.nombre} y por el tiempo que dedicaste a nuestro proceso de selección.

Después de una cuidadosa y exhaustiva evaluación de todos los candidatos, hemos tomado la difícil decisión de continuar con otros perfiles cuya experiencia y habilidades se ajustan de manera más específica a los requisitos particulares de esta posición.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 IMPORTANTE: ESTA NO ES UNA EVALUACIÓN DE TU VALOR
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Queremos enfatizar que esta decisión NO refleja tu valor como profesional ni cuestiona tus capacidades y competencias.

El proceso de selección involucra múltiples factores:
• Requisitos muy específicos del puesto
• Experiencia en áreas particulares
• Disponibilidad inmediata
• Compatibilidad cultural y organizacional
• Nivel de especialización requerido
• Presupuesto y estructura salarial
• Necesidades estratégicas del momento

En ocasiones, la decisión se basa en detalles muy específicos que no necesariamente reflejan la calidad de tu perfil profesional.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔄 FUTURAS OPORTUNIDADES
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

¡No pierdas el ánimo! Valoramos tu perfil y queremos que sepas que:

✓ TU PERFIL PERMANECE ACTIVO en nuestra base de datos de talento
✓ Serás CONSIDERADO AUTOMÁTICAMENTE para futuras vacantes que coincidan con tu experiencia
✓ Te INVITAMOS a postularte nuevamente a otras posiciones que publiquemos
✓ Mantendremos TU INFORMACIÓN actualizada por 12 meses
✓ Podrás ACTUALIZAR tu perfil en cualquier momento

Te animamos a:
• Revisar regularmente nuestras ofertas de empleo
• Seguirnos en redes sociales profesionales
• Visitar nuestro portal de carreras
• Mantenerte atento a nuevas oportunidades

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📈 RECOMENDACIONES PARA TU DESARROLLO PROFESIONAL
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Mientras continúas tu búsqueda laboral, te sugerimos:

🎓 FORMACIÓN CONTINUA
• Actualiza tus conocimientos técnicos
• Obtén certificaciones reconocidas en tu área
• Participa en cursos y talleres especializados
• Aprende nuevas tecnologías y herramientas

💼 DESARROLLO DE HABILIDADES
• Fortalece tus soft skills (comunicación, liderazgo, trabajo en equipo)
• Desarrolla habilidades digitales
• Mejora tu dominio de idiomas
• Practica entrevistas y presentaciones

📄 OPTIMIZA TU PERFIL PROFESIONAL
• Actualiza constantemente tu CV y portafolio
• Mantén activo tu perfil en LinkedIn y otras plataformas
• Solicita recomendaciones de empleadores anteriores
• Documenta tus logros y proyectos exitosos

🌐 NETWORKING
• Asiste a eventos profesionales de tu sector
• Conecta con profesionales de tu área
• Participa en comunidades y grupos especializados
• Mantén relaciones profesionales activas

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🙏 NUESTRO AGRADECIMIENTO
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Valoramos profundamente:
• El tiempo que invertiste en nuestro proceso
• Tu interés genuino en {empresa.nombre}
• La información y documentación que compartiste
• Tu profesionalismo durante todo el proceso

Fue un placer conocer tu trayectoria y perfil profesional.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

{candidato.first_name}, te deseamos el mayor de los éxitos en tu búsqueda laboral y en todos tus proyectos profesionales futuros.

Estamos seguros de que encontrarás una excelente oportunidad donde tu talento, experiencia y dedicación serán plenamente aprovechados y valorados.

Las puertas de {empresa.nombre} permanecen abiertas para futuras oportunidades.

¡Mucho éxito!

Con los mejores deseos,

Equipo de Gestión de Talento Humano
{empresa.nombre}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Sistema de Gestión de Candidatos | TalentoHub
Correo generado automáticamente el {timezone.now().strftime('%d/%m/%Y a las %H:%M')}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
                }
            }
            
            template = templates.get(nuevo_estado)
            correo_enviado = False
            
            if template:
                logger.info(f"📧 Encolando envío SMTP para estado '{nuevo_estado}' → {candidato.email}")
                enviado_ok = send_plain_email(
                    subject=template["asunto"],
                    message=template["mensaje"],
                    recipient_list=[candidato.email],
                    fail_silently=False,
                    async_send=False,
                )
                correo_enviado = bool(enviado_ok)
                print(f"📬 Resultado send_plain_email para {candidato.email}: {correo_enviado}")
                logger.info(f"📧 Resultado envío correo estado ({nuevo_estado}): {correo_enviado}")
            else:
                logger.warning(f"⚠️ No existe plantilla de correo para el estado '{nuevo_estado}'.")
                    
        except Exception as e:
            print(f"❌ Error enviando correo de estado '{nuevo_estado}': {e}")
            logger.error(f"❌ Error enviando correo de estado '{nuevo_estado}': {e}")
            import traceback
            print(traceback.format_exc())
            logger.error(traceback.format_exc())
            # No fallar la actualización si falla el correo
        
        logger.info(f"✅ Estado actualizado: {estado_anterior} → {nuevo_estado}")

    return Response({
        "message": "Estado actualizado correctamente.",
        "correo_enviado": bool(locals().get("correo_enviado", False)),
        "postulacion_id": postulacion.id,
        "nuevo_estado": nuevo_estado
    })

# ----------------------------
# Contactar candidato
# ----------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
def contactar_candidato(request, postulacion_id):
    """
    Endpoint para que el reclutador (RRHH) o admin registre un comentario
    en la postulación sin enviar correo (los correos se envían automáticamente al cambiar estado).
    URL típica: POST /reclutador/postulaciones/<id>/contactar/
    Body (JSON):
    {
        "asunto": "Nota sobre entrevista",
        "mensaje": "El candidato confirmó disponibilidad..."
    }
    """

    # 1️⃣ Verificar rol de quien llama (admin o RRHH)
    caller_role_raw = getattr(request.user, 'role', None) or get_supabase_role(request.user)
    caller_role = normalize_role(caller_role_raw)
    print(f"👤 Caller role raw: {caller_role_raw} -> normalized: {caller_role}")

    if caller_role not in (Roles.ADMIN, Roles.EMPLEADO_RRHH):
        return Response(
            {'error': 'Solo reclutadores (RRHH) o administradores pueden registrar notas.'},
            status=403
        )

    # 2️⃣ Obtener la postulación
    postulacion = get_object_or_404(Postulacion, id=postulacion_id)

    # 3️⃣ Si es RRHH, comprobar que esté asignado a la vacante
    if caller_role == Roles.EMPLEADO_RRHH:
        asignado = VacanteRRHH.objects.filter(
            vacante=postulacion.vacante,
            rrhh_user=request.user
        ).exists()

        if not asignado:
            return Response(
                {'error': 'No tienes permisos sobre esta vacante/postulación.'},
                status=403
            )

    # 4️⃣ Tomar asunto y mensaje del body
    data = request.data
    asunto = data.get('asunto') or 'Nota interna'
    mensaje = data.get('mensaje')

    if not mensaje:
        return Response(
            {'error': 'El campo "mensaje" es obligatorio.'},
            status=400
        )

    # 5️⃣ Guardar comentario en la postulación (historial) sin enviar correo
    marca_tiempo = timezone.now().strftime("%Y-%m-%d %H:%M")
    comentario_nuevo = (
        f"[{marca_tiempo}] {request.user.email} registró nota:\n"
        f"Asunto: {asunto}\n"
        f"Mensaje: {mensaje}\n\n"
    )

    # Asegurarnos de no romper si por alguna razón no existe el campo
    if hasattr(postulacion, "comentarios"):
        if postulacion.comentarios:
            postulacion.comentarios += comentario_nuevo
        else:
            postulacion.comentarios = comentario_nuevo
        postulacion.save(update_fields=["comentarios"])

    # 6️⃣ Respuesta
    return Response(
        {'message': 'Nota registrada correctamente en la postulación'},
        status=200
    )


# ----------------------------
# Permisos
# ----------------------------

class IsOwner(permissions.BasePermission):
    """Permiso simple: solo el propietario puede modificar/ver este objeto."""
    def has_object_permission(self, request, view, obj):
        # Soporta objetos con atributo 'owner' o 'user'
        owner = getattr(obj, 'owner', None) or getattr(obj, 'user', None)
        return owner == request.user


def upload_to_supabase_with_retry(bucket_path, file_bytes, file_name, content_type,
                                  max_retries=3, initial_backoff=1.0):
    """Compatibilidad: conserva nombre, pero sube archivo a Cloudinary."""
    _ = (max_retries, initial_backoff)
    url = _upload_to_cloudinary(
        file_bytes=file_bytes,
        folder=bucket_path,
        filename=file_name,
        resource_type="raw" if "pdf" in (content_type or "").lower() else "auto",
    )
    return {"url": url}

class IsAdmin(permissions.BasePermission):
    """Solo administradores pueden gestionar usuarios"""
    def has_permission(self, request, view):
        user_role = normalize_role(getattr(request.user, 'role', None) or get_supabase_role(request.user))
        return user_role == Roles.ADMIN


class IsAdminUserOrReadSelf(permissions.BasePermission):
    """
    Permiso compuesto:
    - Admin: puede listar, crear, actualizar y eliminar usuarios.
    - Usuario normal: solo puede ver y editar su propio perfil.
    """
    def has_permission(self, request, view):
        user_role = normalize_role(getattr(request.user, 'role', None) or get_supabase_role(request.user))
        if user_role == Roles.ADMIN:
            return True
        return request.method in permissions.SAFE_METHODS or view.action in ['retrieve', 'update', 'partial_update']

    def has_object_permission(self, request, view, obj):
        user_role = normalize_role(getattr(request.user, 'role', None) or get_supabase_role(request.user))
        if user_role == Roles.ADMIN:
            return True
        return obj == request.user

from rest_framework.permissions import BasePermission

class IsAdminOrRRHH(BasePermission):
      def has_permission(self, request, view):
        user_role = normalize_role(getattr(request.user, 'role', None) or get_supabase_role(request.user))
        return user_role in (Roles.ADMIN, Roles.EMPLEADO_RRHH)

# ----------------------------
# Home
# ----------------------------
def home(request):
    return HttpResponse("¡Hola, Django está funcionando correctamente!")


# Test endpoint para verificar conexión a Supabase
class TestSupabaseView(APIView):
    permission_classes = [permissions.AllowAny]

    def get(self, request):
        try:
            response = cloudinary.api.ping()
            return Response({
                "message": "Conexión a Cloudinary exitosa",
                "data": response
            })
        except Exception as e:
            return Response({
                "message": "Error al conectar a Cloudinary",
                "error": str(e)
            }, status=500)


# ----------------------------
# Registro de usuarios
# ----------------------------
class RegisterView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = UserSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            return Response({
                "user": UserSerializer(user).data,
                "message": "Usuario creado exitosamente"
            }, status=201)
        return Response(serializer.errors, status=400)


# ----------------------------
# Login con JWT (ver CustomTokenObtainPairSerializer más abajo)
# ----------------------------
# ----------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
def asignar_rrhh_vacante(request):
    """Permite al admin asignar un empleado RRHH a una vacante específica.

    Body esperado:
    {
        "vacante_id": 1,
        "rrhh_email": "empleado@empresa.com"
    }
    """
    caller_role = normalize_role(getattr(request.user, 'role', None) or get_supabase_role(request.user))
    if caller_role != Roles.ADMIN:
        return Response({'error': 'Solo el administrador puede asignar RRHH a vacantes.'}, status=403)

    vacante_id = request.data.get('vacante_id')
    rrhh_email = request.data.get('rrhh_email')

    if not vacante_id or not rrhh_email:
        return Response({'error': 'Debes enviar vacante_id y rrhh_email.'}, status=400)

    # Validar que la vacante existe
    try:
        vacante = Vacante.objects.get(id=vacante_id)
    except Vacante.DoesNotExist:
        return Response({'error': 'Vacante no encontrada.'}, status=404)

    # Obtener el usuario RRHH por email
    try:
        rrhh_user = User.objects.get(email=rrhh_email)
    except User.DoesNotExist:
        return Response({'error': 'Usuario RRHH no encontrado con ese email.'}, status=404)

    # Validar que el usuario tenga rol RRHH
    rrhh_role = normalize_role(getattr(rrhh_user, 'role', None) or get_supabase_role(rrhh_user))
    if rrhh_role != Roles.EMPLEADO_RRHH:
        return Response({'error': f'El usuario {rrhh_email} no tiene rol RRHH.'}, status=400)

    # Crear o recuperar la asignación
    asignacion, created = VacanteRRHH.objects.get_or_create(
        vacante=vacante,
        rrhh_user=rrhh_user
    )

    if created:
        msg = f'RRHH {rrhh_email} asignado a vacante {vacante.titulo}.'
    else:
        msg = f'RRHH {rrhh_email} ya estaba asignado a vacante {vacante.titulo}.'

    return Response({'message': msg, 'asignacion_id': asignacion.id}, status=200)
# Obtener postulaciones asignadas a un usuario RRHH
@api_view(['GET'])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
def obtener_postulaciones_asignadas_rrhh(request):
    """Devuelve todas las postulaciones de las vacantes asignadas al RRHH autenticado.

    Requiere rol RRHH.
    """
    caller_role = normalize_role(getattr(request.user, 'role', None) or get_supabase_role(request.user))
    if caller_role != Roles.EMPLEADO_RRHH:
        return Response({'error': 'Solo usuarios RRHH pueden ver sus postulaciones asignadas.'}, status=403)

    # Obtener vacantes asignadas al RRHH
    asignaciones = VacanteRRHH.objects.filter(rrhh_user=request.user).select_related('vacante')
    vacantes_ids = [a.vacante.id for a in asignaciones]

    if not vacantes_ids:
        return Response({'postulaciones': []}, status=200)

    # Obtener todas las postulaciones de esas vacantes
    postulaciones = Postulacion.objects.filter(vacante_id__in=vacantes_ids).select_related(
        'candidato', 'vacante', 'empresa'
    )

    serializer = PostulacionSerializer(postulaciones, many=True)
    return Response({'postulaciones': serializer.data}, status=200)


@api_view(['GET'])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
def mis_postulaciones(request):
    """Lista todas las postulaciones del candidato autenticado con detalle completo de vacante y empresa."""
    caller_role = normalize_role(getattr(request.user, 'role', None) or get_supabase_role(request.user))
    
    if caller_role != Roles.CANDIDATO:
        return Response({'error': 'Solo candidatos pueden ver sus postulaciones.'}, status=403)

    postulaciones = Postulacion.objects.filter(candidato=request.user).select_related(
        'vacante', 'vacante__id_empresa', 'empresa'
    ).order_by('-fecha_postulacion')

    data = []
    for postulacion in postulaciones:
        vacante = postulacion.vacante
        empresa = vacante.id_empresa if vacante and vacante.id_empresa else postulacion.empresa

        vacante_data = None
        if vacante:
            vacante_data = {
                'id': vacante.id,
                'titulo': vacante.titulo,
                'descripcion': vacante.descripcion,
                'requisitos': vacante.requisitos,
                'fecha_expiracion': vacante.fecha_expiracion,
                'estado': vacante.estado,
                'ubicacion': vacante.ubicacion,
                'salario': vacante.salario,
                'experiencia': vacante.experiencia,
                'beneficios': vacante.beneficios,
                'tipo_jornada': vacante.tipo_jornada,
                'modalidad_trabajo': vacante.modalidad_trabajo,
                'created_at': vacante.created_at,
                'updated_at': vacante.updated_at,
            }

            if empresa:
                vacante_data['empresa'] = {
                    'id': empresa.id,
                    'nombre': empresa.nombre,
                    'nit': empresa.nit,
                    'direccion': empresa.direccion,
                    'logo_url': empresa.logo_url,
                }

        data.append({
            'id': postulacion.id,
            'estado': postulacion.estado,
            'cv_url': postulacion.cv_url,
            'fecha_postulacion': postulacion.fecha_postulacion,
            'comentarios': postulacion.comentarios,
            'vacante': vacante_data,
            'empresa_nombre': empresa.nombre if empresa else None,
            'empresa_id': empresa.id if empresa else None,
        })

    return Response({
        'count': len(data),
        'postulaciones': data
    }, status=200)

# ViewSet para Empresas (CRUD)
class EmpresaViewSet(viewsets.ModelViewSet):
    """CRUD completo para empresas. Solo admins."""
    queryset = Empresa.objects.all()
    serializer_class = EmpresaSerializer
    permission_classes = [IsAuthenticated, IsAdmin, CheckUserInactivityPermission]


# ViewSet para Postulaciones (readonly para candidatos, write para RRHH/admin)
class PostulacionViewSet(viewsets.ModelViewSet):
    """CRUD para postulaciones. Filtrado automático según rol."""
    queryset = Postulacion.objects.all()
    serializer_class = PostulacionSerializer
    permission_classes = [IsAuthenticated, CheckUserInactivityPermission]

    def get_queryset(self):
        user = self.request.user
        role = normalize_role(getattr(user, 'role', None) or get_supabase_role(user))

        if role == Roles.ADMIN:
            return Postulacion.objects.all()
        elif role == Roles.EMPLEADO_RRHH:
            # RRHH ve solo las postulaciones de vacantes asignadas
            asignaciones = VacanteRRHH.objects.filter(rrhh_user=user)
            vacantes_ids = [a.vacante.id for a in asignaciones]
            return Postulacion.objects.filter(vacante_id__in=vacantes_ids)
        elif role == Roles.CANDIDATO:
            # Candidato ve solo sus propias postulaciones
            return Postulacion.objects.filter(candidato=user)
        else:
            return Postulacion.objects.none()


# ViewSet para Entrevistas
class EntrevistaViewSet(viewsets.ModelViewSet):
    queryset = Entrevista.objects.all()
    serializer_class = EntrevistaSerializer
    permission_classes = [IsAuthenticated, IsAdminOrRRHH, CheckUserInactivityPermission]

    def get_queryset(self):
        user = self.request.user
        role = normalize_role(getattr(user, 'role', None) or get_supabase_role(user))

        if role == Roles.ADMIN:
            return Entrevista.objects.all()
        elif role == Roles.EMPLEADO_RRHH:
            # RRHH ve solo entrevistas de vacantes asignadas
            asignaciones = VacanteRRHH.objects.filter(rrhh_user=user)
            vacantes_ids = [a.vacante.id for a in asignaciones]
            postulaciones_ids = Postulacion.objects.filter(vacante_id__in=vacantes_ids).values_list('id', flat=True)
            return Entrevista.objects.filter(postulacion_id__in=postulaciones_ids)
        else:
            return Entrevista.objects.none()


class SessionHeartbeatView(APIView):
    permission_classes = [IsAuthenticated, CheckUserInactivityPermission]

    def post(self, request):
        try:
            from django.core.cache import cache
            from django.utils import timezone
            cache_key = f'user_activity_{request.user.id}'
            activity_cache_ttl = getattr(settings, 'INACTIVITY_CACHE_TTL', 86400)
            cache.set(cache_key, timezone.now().isoformat(), activity_cache_ttl)
        except Exception:
            pass

        return Response({"detail": "Actividad registrada correctamente."}, status=200)


# Perfil del usuario autenticado
@api_view(["GET", "PUT", "PATCH"])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
def mi_perfil(request):
    """
    GET: Devuelve la información del perfil del usuario autenticado.
    PUT/PATCH: Actualiza la información del perfil.
    """
    user = request.user

    if request.method == "GET":
        serializer = PerfilUsuarioSerializer(user)
        return Response(serializer.data)

    elif request.method in ["PUT", "PATCH"]:
        serializer = PerfilUsuarioSerializer(user, data=request.data, partial=(request.method == "PATCH"))
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=400)


# Vista para actualizar la hoja de vida (CV)
@api_view(['POST'])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
def actualizar_hoja_vida(request):
    """
    Permite al usuario subir o actualizar su archivo de hoja de vida.

    Body esperado (form-data):
    - hoja_de_vida: archivo PDF

    Sube a Cloudinary y actualiza la URL en el campo hoja_de_vida del perfil.
    """
    user = request.user
    perfil, _ = PerfilUsuario.objects.get_or_create(user=user)

    # Validar archivo
    archivo_cv = request.FILES.get('hoja_de_vida')
    if not archivo_cv:
        return Response({'error': 'Debe enviar el archivo "hoja_de_vida".'}, status=400)

    # Validar el archivo
    try:
        validate_hoja_vida(archivo_cv)
    except Exception as e:
        return Response({'error': str(e)}, status=400)

    # Subir a Cloudinary
    try:
        contenido = archivo_cv.read()
        url_final = _upload_to_cloudinary(
            file_bytes=contenido,
            folder=f"perfiles/{user.id}/hoja_vida",
            filename=archivo_cv.name,
            resource_type="raw",
        )

        # Actualizar perfil
        perfil.hoja_de_vida = url_final
        perfil.save()

        return Response({
            'message': 'Hoja de vida actualizada exitosamente.',
            'url': url_final
        }, status=200)

    except Exception as e:
        return Response({'error': f'Error subiendo archivo: {str(e)}'}, status=500)


# Crear favorito
@api_view(['POST'])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
def crear_favorito(request):
    """
    Permite al usuario autenticado marcar una vacante como favorita.

    Body esperado:
    {
        "vacante_id": 1
    }
    """
    vacante_id = request.data.get('vacante_id')

    if not vacante_id:
        return Response({'error': 'Debe enviar "vacante_id".'}, status=400)

    try:
        vacante = Vacante.objects.get(id=vacante_id)
    except Vacante.DoesNotExist:
        return Response({'error': 'Vacante no encontrada.'}, status=404)

    # Crear o recuperar favorito
    favorito, created = Favorito.objects.get_or_create(usuario=request.user, vacante=vacante)

    if created:
        return Response({'message': 'Vacante marcada como favorita.'}, status=201)
    else:
        return Response({'message': 'Esta vacante ya está en tus favoritos.'}, status=200)


# Listar favoritos
@api_view(['GET'])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
def listar_favoritos(request):
    """
    Devuelve la lista de vacantes favoritas del usuario autenticado.
    """
    favoritos = Favorito.objects.filter(usuario=request.user).select_related('vacante')
    serializer = FavoritoSerializer(favoritos, many=True)
    return Response(serializer.data)


# Eliminar favorito
@api_view(['DELETE'])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
def eliminar_favorito(request, vacante_id):
    """
    Elimina una vacante de los favoritos del usuario autenticado.
    """
    try:
        favorito = Favorito.objects.get(usuario=request.user, vacante_id=vacante_id)
        favorito.delete()
        return Response({'message': 'Vacante eliminada de favoritos.'}, status=200)
    except Favorito.DoesNotExist:
        return Response({'error': 'Favorito no encontrado.'}, status=404)


# ----------------------------
# Perfil de candidato (público, visto por RRHH/Admin)
# ----------------------------
@api_view(['GET'])
@permission_classes([IsAuthenticated, IsAdminOrRRHH, CheckUserInactivityPermission])
def perfil_candidato(request, candidato_id):
    """
    Devuelve el perfil completo de un candidato.
    Solo accesible por Admin o RRHH.
    """
    try:
        candidato = User.objects.get(id=candidato_id)
    except User.DoesNotExist:
        return Response({'error': 'Candidato no encontrado.'}, status=404)

    # Verificar que el candidato tenga rol de candidato
    role = normalize_role(getattr(candidato, 'role', None) or get_supabase_role(candidato))
    if role != Roles.CANDIDATO:
        return Response({'error': 'El usuario no es un candidato.'}, status=400)

    serializer = PerfilUsuarioSerializer(candidato)
    return Response(serializer.data)

# ----------------------------
# Restablecimiento de contraseña        
# ----------------------------
@api_view(['POST'])
@permission_classes([permissions.AllowAny])
def reset_password_confirm(request):
    """
    Confirma el restablecimiento de contraseña con el token.

    Body esperado:
    {
        "uid": "...",
        "token": "...",
        "new_password": "nueva_contraseña"
    }
    """
    uid = request.data.get('uid')
    token = request.data.get('token')
    new_password = request.data.get('new_password')

    if not all([uid, token, new_password]):
        return Response({'error': 'Debe enviar uid, token y new_password.'}, status=400)

    try:
        user_id = force_str(urlsafe_base64_decode(uid))
        user = User.objects.get(pk=user_id)
    except (TypeError, ValueError, OverflowError, User.DoesNotExist):
        return Response({'error': 'Enlace inválido.'}, status=400)

    if not default_token_generator.check_token(user, token):
        return Response({'error': 'Token inválido o expirado.'}, status=400)

    # Cambiar contraseña
    user.set_password(new_password)
    user.save()

    return Response({'message': 'Contraseña restablecida exitosamente.'}, status=200)


# ----------------------------
# Permisos
# ----------------------------

class IsOwner(permissions.BasePermission):
    """Permiso simple: solo el propietario puede modificar/ver este objeto."""
    def has_object_permission(self, request, view, obj):
        # Soporta objetos con atributo 'owner' o 'user'
        owner = getattr(obj, "owner", None) or getattr(obj, "user", None)
        return bool(owner and owner == request.user)

def upload_to_supabase_with_retry(bucket_path, file_bytes, file_name, content_type,
                                  max_retries=3, initial_backoff=1.0):
    """Compatibilidad: conserva nombre, pero sube archivo a Cloudinary."""
    _ = (max_retries, initial_backoff)
    url = _upload_to_cloudinary(
        file_bytes=file_bytes,
        folder=bucket_path,
        filename=file_name,
        resource_type="raw" if "pdf" in (content_type or "").lower() else "auto",
    )
    return {"url": url}


# ----------------------------
# Contactar candidato
# ----------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
def contactar_candidato(request, postulacion_id):
    """
    Endpoint para que el reclutador (RRHH) o admin registre un comentario
    en la postulación sin enviar correo (los correos se envían automáticamente al cambiar estado).
    URL típica: POST /reclutador/postulaciones/<id>/contactar/
    Body (JSON):
    {
        "asunto": "Nota sobre entrevista",
        "mensaje": "El candidato confirmó disponibilidad..."
    }
    """

    # 1️⃣ Verificar rol de quien llama (admin o RRHH)
    caller_role_raw = getattr(request.user, 'role', None) or get_supabase_role(request.user)
    caller_role = normalize_role(caller_role_raw)
    print(f"👤 Caller role raw: {caller_role_raw} -> normalized: {caller_role}")

    if caller_role not in (Roles.ADMIN, Roles.EMPLEADO_RRHH):
        return Response(
            {'error': 'Solo reclutadores (RRHH) o administradores pueden registrar notas.'},
            status=403
        )

    # 2️⃣ Obtener la postulación
    postulacion = get_object_or_404(Postulacion, id=postulacion_id)

    # 3️⃣ Si es RRHH, comprobar que esté asignado a la vacante
    if caller_role == Roles.EMPLEADO_RRHH:
        asignado = VacanteRRHH.objects.filter(
            vacante=postulacion.vacante,
            rrhh_user=request.user
        ).exists()

        if not asignado:
            return Response(
                {'error': 'No tienes permisos sobre esta vacante/postulación.'},
                status=403
            )

    # 4️⃣ Tomar asunto y mensaje del body
    data = request.data
    asunto = data.get('asunto') or 'Nota interna'
    mensaje = data.get('mensaje')

    if not mensaje:
        return Response(
            {'error': 'El campo "mensaje" es obligatorio.'},
            status=400
        )

    # 5️⃣ Guardar comentario en la postulación (historial) sin enviar correo
    marca_tiempo = timezone.now().strftime("%Y-%m-%d %H:%M")
    comentario_nuevo = (
        f"[{marca_tiempo}] {request.user.email} registró nota:\n"
        f"Asunto: {asunto}\n"
        f"Mensaje: {mensaje}\n\n"
    )

    # Asegurarnos de no romper si por alguna razón no existe el campo
    if hasattr(postulacion, "comentarios"):
        if postulacion.comentarios:
            postulacion.comentarios += comentario_nuevo
        else:
            postulacion.comentarios = comentario_nuevo
        postulacion.save(update_fields=["comentarios"])

    # 6️⃣ Respuesta
    return Response(
        {'message': 'Nota registrada correctamente en la postulación'},
        status=200
    )


# ----------------------------
# Permisos
# ----------------------------

class IsOwner(permissions.BasePermission):
    """Permiso simple: solo el propietario puede modificar/ver este objeto."""
    def has_object_permission(self, request, view, obj):
        # Soporta objetos con atributo 'owner' o 'user'
        owner = getattr(obj, "owner", None) or getattr(obj, "user", None)
        return bool(owner and owner == request.user)

def upload_to_supabase_with_retry(bucket_path, file_bytes, file_name, content_type,
                                  max_retries=3, initial_backoff=1.0):
    """Compatibilidad: conserva nombre, pero sube archivo a Cloudinary."""
    _ = (max_retries, initial_backoff)
    url = _upload_to_cloudinary(
        file_bytes=file_bytes,
        folder=bucket_path,
        filename=file_name,
        resource_type="raw" if "pdf" in (content_type or "").lower() else "auto",
    )
    return {"url": url}

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

from rest_framework.permissions import BasePermission

class IsAdminOrRRHH(BasePermission):
      def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        role = normalize_role(getattr(user, "role", None) or get_supabase_role(user))
        return role in [Roles.ADMIN, Roles.EMPLEADO_RRHH]

# ----------------------------
# Home
# ----------------------------
def home(request):
    return HttpResponse("¡Hola, Django está funcionando correctamente!")


# Test endpoint para verificar conexión a Cloudinary
class TestSupabaseView(APIView):
    permission_classes = [permissions.AllowAny]
    
    def get(self, request):
        try:
            ping = cloudinary.api.ping()
            
            return Response({
                "status": "✅ Conectado a Cloudinary",
                "cloud_name": os.getenv("CLOUDINARY_CLOUD_NAME"),
                "ping": ping,
            })
        except Exception as e:
            return Response({
                "status": "❌ Error conectando a Cloudinary",
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ----------------------------
# Función auxiliar para enviar email de bienvenida
# ----------------------------
def send_welcome_email(user_email, user_name):
    """Envia un email de bienvenida usando el backend configurado"""
    try:
        send_template_email(
            template_key="welcome",
            recipient_list=[user_email],
            context={
                "user_name": user_name,
                "login_url": "http://localhost:3000/login",
            },
            fail_silently=True,
            async_send=True,
        )
        print(f'✅ Email de bienvenida en cola para {user_email}')
        return True
    except Exception as e:
        print(f'❌ Error enviando email a {user_email}: {str(e)}')
        import traceback
        traceback.print_exc()
        return False


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
            user = serializer.create(serializer.validated_data)  # Aquí se guarda el role correctamente
            
            # Enviar email de bienvenida en background (no bloqueante)
            send_welcome_email(user.email, user.username)
            
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        out = UserSerializer(user).data
        return Response(out, status=status.HTTP_201_CREATED)


# ----------------------------
# Login con JWT
# ----------------------------

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

        # Obtener role directamente de la BD (el campo existe en auth_user pero no en el modelo Django)
        from django.db import connection
        role = Roles.CANDIDATO
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT role FROM auth_user WHERE id = %s', [user.id])
                row = cursor.fetchone()
                if row and row[0]:
                    role = normalize_role(row[0]) or Roles.CANDIDATO
        except Exception:
            pass

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
    
    def post(self, request, *args, **kwargs):
        # Llamar al flujo estándar de obtención de tokens
        response = super().post(request, *args, **kwargs)
        try:
            if response.status_code == 200 and isinstance(response.data, dict):
                user_info = response.data.get("user")
                if user_info and user_info.get("id"):
                    from django.core.cache import cache
                    from django.utils import timezone
                    from django.conf import settings as dj_settings
                    user_id = user_info.get("id")
                    cache_key = f'user_activity_{user_id}'
                    activity_cache_ttl = getattr(dj_settings, 'INACTIVITY_CACHE_TTL', 86400)
                    cache.set(cache_key, timezone.now().isoformat(), activity_cache_ttl)
        except Exception:
            pass

        return response
# ----------------------------
# Empresa
# ----------------------------
class EmpresaViewSet(viewsets.ModelViewSet):
    serializer_class = EmpresaSerializer
    permission_classes = [permissions.IsAuthenticated, CheckUserInactivityPermission]

    def get_queryset(self):
        # Solo muestra las empresas del usuario autenticado
        return Empresa.objects.filter(owner=self.request.user)

    def get_serializer_context(self):
        context = super().get_serializer_context()
        context["request"] = self.request
        return context

    def create(self, request, *args, **kwargs):
        # Solo usuarios admin pueden crear empresas
        role = normalize_role(getattr(request.user, "role", None) or get_supabase_role(request.user))
        if role != Roles.ADMIN:
            return Response(
                {"detail": "Solo los usuarios con rol admin pueden crear empresas."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().create(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        # Validar que sea propietario de la empresa
        empresa = self.get_object()
        if empresa.owner != request.user:
            return Response(
                {"detail": "No tienes permiso para modificar esta empresa."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        # Validar que sea propietario de la empresa
        empresa = self.get_object()
        if empresa.owner != request.user:
            return Response(
                {"detail": "No tienes permiso para eliminar esta empresa."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().destroy(request, *args, **kwargs)

    def perform_create(self, serializer):
        """
        Cuando un usuario crea una empresa:
        1️⃣ Se guarda la empresa con su usuario como owner (lo hace el serializer).
        2️⃣ Se actualiza su rol en Django usando SQL raw.
        3️⃣ Se sincroniza el rol y grupo 'admin' en Supabase.
        """
        user = self.request.user

        # 🔹 IMPORTANTE: ya NO pasamos owner=user aquí
        empresa = serializer.save()

        # --- 1️⃣ Actualizar rol en la BD (usando SQL raw porque Django no reconoce el campo role) ---
        from django.db import connection
        try:
            with connection.cursor() as cursor:
                cursor.execute('UPDATE auth_user SET role = %s WHERE id = %s', [Roles.ADMIN, user.id])
            print(f"✅ Rol del usuario '{user.username}' actualizado a ADMIN en la BD")
        except Exception as e:
            print(f"⚠️ Error al actualizar rol en la BD: {str(e)}")

        # --- 2️⃣ Sincronizar grupo en Django ---
        try:
            admin_group, _ = Group.objects.get_or_create(name=Roles.ADMIN)
            user.groups.add(admin_group)
            print(f"✅ Usuario {user.email} asignado correctamente al grupo 'admin' en Django.")
        except Exception as e:
            print(f"⚠️ Error actualizando grupo en Django: {e}")

        return empresa
@api_view(['GET'])
@permission_classes([permissions.AllowAny])  # Permite acceso a cualquier usuario
def listar_empresas(request):
    """Lista todas las empresas sin restricciones de rol."""

    empresas = Empresa.objects.all()

    # Serializamos las empresas
    data = []
    for e in empresas:
        data.append({
            "id": e.id,
            "nombre": e.nombre,
            "nit": e.nit,
            "direccion": e.direccion,
            "logo_url": e.logo_url,
            "descripcion": e.descripcion,
        })

    return JsonResponse(data, safe=False, status=200)
# ----------------------------
# Asignar RRHH a Vacante
# ----------------------------

User = get_user_model()

@api_view(['POST'])
@permission_classes([IsAuthenticated, CheckUserInactivityPermission])
def asignar_rrhh_a_vacante(request, vacante_id):
    # Verificar si el usuario tiene rol 'admin' (resolver role de forma segura)
    caller_role_raw = getattr(request.user, 'role', None) or get_supabase_role(request.user)
    caller_role = normalize_role(caller_role_raw)
    print(f"🔎 Caller role raw: {caller_role_raw} -> normalized: {caller_role}")
    if caller_role != Roles.ADMIN:
        return Response({'error': 'Solo un administrador puede asignar RRHH a vacantes.'}, status=status.HTTP_403_FORBIDDEN)

    # Obtener la vacante
    vacante = get_object_or_404(Vacante, id=vacante_id)

    # Verificar que la vacante pertenece a la empresa del admin que hace la petición
    empresa = getattr(vacante, 'id_empresa', None)
    if not empresa or getattr(empresa, 'owner_id', None) != request.user.id:
        return Response({'error': 'No tiene permisos para asignar RRHH en esta vacante (pertenece a otra empresa).'}, status=status.HTTP_403_FORBIDDEN)

    # Obtener el RRHH a asignar: aceptamos `user_id` o `email` en el body.
    rrhh_id = request.data.get('user_id')
    rrhh_email = request.data.get('email')

    if not rrhh_id and not rrhh_email:
        return Response({'error': 'Debe enviar "user_id" o "email" del RRHH a asignar.'}, status=status.HTTP_400_BAD_REQUEST)

    # Resolver usuario por email si se proporcionó (útil para pruebas que buscan por correo)
    rrhh_user = None
    if rrhh_email:
        rrhh_user = User.objects.filter(email=rrhh_email).first()
        if not rrhh_user:
            return Response({'error': f'No se encontró usuario con email {rrhh_email}.'}, status=status.HTTP_404_NOT_FOUND)
    else:
        rrhh_user = get_object_or_404(User, id=rrhh_id)

    # Comprobar rol del RRHH (usar atributo Django si existe, sino consultar Supabase)
    rrhh_role_raw = getattr(rrhh_user, 'role', None) or get_supabase_role(rrhh_user)
    rrhh_role = normalize_role(rrhh_role_raw)
    print(f"🔎 RRHH role raw: {rrhh_role_raw} -> normalized: {rrhh_role}")
    if rrhh_role != Roles.EMPLEADO_RRHH:
        return Response({'error': 'El usuario especificado no tiene el rol de RRHH.'}, status=status.HTTP_400_BAD_REQUEST)
    # --- Validación: RRHH pertenece a la misma empresa que la vacante ---
    try:
        vacante_empresa_id = None
        if getattr(vacante, 'id_empresa_id', None):
            vacante_empresa_id = int(vacante.id_empresa_id)
        elif getattr(vacante, 'id_empresa', None) and getattr(vacante.id_empresa, 'id', None):
            vacante_empresa_id = int(vacante.id_empresa.id)
    except Exception:
        vacante_empresa_id = None

    rrhh_empresa_id = get_supabase_empresa_id(rrhh_user)
    try:
        rrhh_empresa_id = int(rrhh_empresa_id) if rrhh_empresa_id is not None else None
    except Exception:
        rrhh_empresa_id = None

    # Comprueba si el RRHH es owner en Django de la empresa de la vacante
    rrhh_is_owner = False
    try:
        if vacante_empresa_id is not None:
            rrhh_is_owner = Empresa.objects.filter(id=vacante_empresa_id, owner=rrhh_user).exists()
    except Exception:
        rrhh_is_owner = False

    logger.debug("Validación empresa: vacante_empresa_id=%s rrhh_empresa_id=%s rrhh_is_owner=%s rrhh_id=%s", vacante_empresa_id, rrhh_empresa_id, rrhh_is_owner, getattr(rrhh_user, 'id', None))

    if not ((vacante_empresa_id is not None and rrhh_empresa_id is not None and int(vacante_empresa_id) == int(rrhh_empresa_id)) or rrhh_is_owner):
        return Response({'error': 'El RRHH no pertenece a la empresa de la vacante.', 'vacante_empresa_id': vacante_empresa_id, 'rrhh_empresa_id': rrhh_empresa_id, 'rrhh_is_owner': rrhh_is_owner}, status=status.HTTP_400_BAD_REQUEST)

    # Verificar si ya está asignado (evitar duplicados) — usar el modelo VacanteRRHH
    if VacanteRRHH.objects.filter(vacante=vacante, rrhh_user=rrhh_user).exists():
        return Response({'error': f'El RRHH {rrhh_user.username} ya está asignado a esta vacante.'}, status=status.HTTP_400_BAD_REQUEST)

    # Crear la asignación (guardamos el id en la tabla como antes)
    try:
        asignacion = VacanteRRHH.objects.create(vacante=vacante, rrhh_user=rrhh_user)
    except Exception as e:
        logger.exception("Error creando asignacion RRHH-vacante")
        detail = str(e) if settings.DEBUG else "Error interno"
        return Response(
            {
                'error': 'No se pudo asignar el usuario a la vacante. Intente nuevamente.',
                'detail': detail,
                'hint': "Revise migraciones pendientes con 'python manage.py migrate'.",
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    return Response({
        'message': f'El RRHH {rrhh_user.username} ({rrhh_user.email}) ha sido asignado correctamente a la vacante {vacante.titulo}.',
        'asignacion_id': asignacion.id,
        'rrhh_id': rrhh_user.id,
        'rrhh_email': rrhh_user.email
    }, status=status.HTTP_201_CREATED)
# ----------------------------
# Usuarios
# ----------------------------
class UserViewSet(viewsets.ModelViewSet):
    queryset = User.objects.all().order_by("-id")
    serializer_class = UserSerializer
    permission_classes = [permissions.IsAuthenticated, IsAdmin, CheckUserInactivityPermission]


class UsuarioViewSet(viewsets.ViewSet):
    """
    Gestión de usuarios con ORM de Django.
    """
    permission_classes = [IsAdminUserOrReadSelf]

    def list(self, request):
        if request.user.role != "admin":
            return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)
        usuarios = User.objects.all().values("id", "username", "email", "first_name", "last_name")
        return Response(list(usuarios), status=status.HTTP_200_OK)

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
        usuario = User.objects.filter(id=pk).first()
        if not usuario:
            return Response({"detail": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        if request.user.role != "admin" and usuario.email != request.user.email:
            return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)
        return Response({
            "id": usuario.id,
            "username": usuario.username,
            "email": usuario.email,
            "first_name": usuario.first_name,
            "last_name": usuario.last_name,
            "role": getattr(usuario, "role", None),
        }, status=status.HTTP_200_OK)

    def partial_update(self, request, pk=None):
        usuario = User.objects.filter(id=pk).first()
        if not usuario:
            return Response({"detail": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        if request.user.role != "admin" and usuario.email != request.user.email:
            return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)

        if request.user.role != "admin":
            forbidden = set(request.data.keys()) & {"rol", "email", "id"}
            if forbidden:
                return Response({"detail": "No autorizado para cambiar esos campos"}, status=status.HTTP_403_FORBIDDEN)

        try:
            for field in ["username", "first_name", "last_name", "email"]:
                if field in request.data:
                    setattr(usuario, field, request.data.get(field))
            if "rol" in request.data and request.user.role == "admin" and hasattr(usuario, "role"):
                usuario.role = normalize_role(request.data.get("rol"))
            usuario.save()
        except Exception as e:
            return Response({"detail": f"Error al actualizar: {e}"}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            "id": usuario.id,
            "username": usuario.username,
            "email": usuario.email,
            "first_name": usuario.first_name,
            "last_name": usuario.last_name,
            "role": getattr(usuario, "role", None),
        }, status=status.HTTP_200_OK)

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

        user_obj = User.objects.filter(email=usuario["email"]).first()
        if not user_obj:
            return Response({"detail": "Usuario creado pero no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        group_obj, _ = Group.objects.get_or_create(name=rol)
        user_obj.groups.add(group_obj)
        return Response({"message": f"Usuario '{usuario['email']}' creado con rol '{rol}'"}, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["patch"], url_path="actualizar_rol")
    def actualizar_rol(self, request, pk=None):
        if request.user.role != "admin":
            return Response({"detail": "No autorizado"}, status=status.HTTP_403_FORBIDDEN)
        nuevo_rol = request.data.get("rol")
        if not nuevo_rol:
            return Response({"detail": "Debe especificar el nuevo rol"}, status=status.HTTP_400_BAD_REQUEST)
        usuario = User.objects.filter(id=pk).first()
        if not usuario:
            return Response({"detail": "Usuario no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        normalized_role = normalize_role(nuevo_rol)
        if hasattr(usuario, "role"):
            usuario.role = normalized_role
            usuario.save(update_fields=["role"])

        group_obj, _ = Group.objects.get_or_create(name=normalized_role)
        usuario.groups.clear()
        usuario.groups.add(group_obj)
        return Response({"message": "Rol actualizado correctamente"}, status=status.HTTP_200_OK)

    
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
        except User.DoesNotExist:
            # No revelar si el email existe o no
            return Response({"message": "Si el correo existe, recibirás un enlace para restablecer tu contraseña."}, 
                            status=status.HTTP_200_OK)

        # Generar token y UID
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))

        frontend_url = getattr(settings, "FRONTEND_URL", "http://localhost:3000").rstrip("/")
        frontend_reset_path = getattr(settings, "FRONTEND_RESET_PASSWORD_PATH", "/reset-password")
        if not str(frontend_reset_path).startswith("/"):
            frontend_reset_path = f"/{frontend_reset_path}"
        query = urlencode({"uid": uid, "token": token})
        reset_link = f"{frontend_url}{frontend_reset_path}?{query}"

        # Enviar correo de restablecimiento con plantilla
        try:
            send_template_email(
                template_key="password_reset",
                recipient_list=[email],
                context={
                    "username": user.username,
                    "reset_link": reset_link,
                },
                fail_silently=False,
            )
            print("📧 Correo enviado correctamente por SMTP")
        except Exception as e:
            print("❌ Error enviando correo:", e)
            return Response({"error": "Error enviando correo"}, status=500)

        return Response({"message": "Si el correo existe, recibirás un enlace para restablecer tu contraseña."},
                     status=status.HTTP_200_OK)
        
class PasswordResetConfirmView(APIView):
    permission_classes = []

    def post(self, request, uidb64=None, token=None):
        # Soporta ambos formatos:
        # 1) /password-reset-confirm/<uidb64>/<token>/ + {"password": "..."}
        # 2) /password-reset-confirm/ + {"uid": "...", "token": "...", "password"|"new_password": "..."}
        uidb64 = uidb64 or request.data.get("uid")
        token = token or request.data.get("token")
        password = request.data.get("password") or request.data.get("new_password")

        if not uidb64 or not token:
            return Response({"detail": "Se requieren uid y token"}, status=status.HTTP_400_BAD_REQUEST)

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
    permission_classes = [permissions.IsAuthenticated, CheckUserInactivityPermission]

    def get(self, request):
        user = request.user
        datos_filtrados = {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "email": user.email,
            "role": normalize_role(getattr(user, "role", None) or get_supabase_role(user)),
            "date_joined": user.date_joined,
            "last_login": user.last_login,
        }

        return Response(datos_filtrados)

    def put(self, request):
        user = request.user
        data = request.data.copy()

        serializer = PerfilSerializer(request.user, data=data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=200)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
    
# DATOS ADICIONALES DEL PERFIL DE USUARIO

class PerfilUsuarioView(APIView):
    permission_classes = [permissions.IsAuthenticated, CheckUserInactivityPermission]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    # ========================================
    #                  GET
    # ========================================
    def get(self, request):
        perfil, _ = PerfilUsuario.objects.get_or_create(user=request.user)

        serializer = PerfilUsuarioSerializer(perfil)
        data = serializer.data
        data.setdefault("telefono", None)
        data.setdefault("documento", None)

        return Response(data)

    # ========================================
    #                  POST
    # ========================================
    def post(self, request):
        perfil, _ = PerfilUsuario.objects.get_or_create(user=request.user)

        try:
            # ======================
            # SUBIR FOTO DE PERFIL
            # ======================
            foto = request.FILES.get("foto_perfil")
            if foto:
                foto_bytes = foto.read()
                public_url = _upload_to_cloudinary(
                    file_bytes=foto_bytes,
                    folder=f"perfiles/{request.user.id}/foto",
                    filename=foto.name,
                    resource_type="image",
                )

                perfil.foto_perfil = public_url
                perfil.save(update_fields=["foto_perfil"])

            # ======================
            # SUBIR HOJA DE VIDA
            # ======================
            hoja = request.FILES.get("hoja_vida")
            if hoja:
                hoja_bytes = hoja.read()
                public_url = _upload_to_cloudinary(
                    file_bytes=hoja_bytes,
                    folder=f"perfiles/{request.user.id}/hoja_vida",
                    filename=hoja.name,
                    resource_type="raw",
                )

                perfil.hoja_vida = public_url
                perfil.save(update_fields=["hoja_vida"])

        except Exception as e:
            print("Error procesando archivos:", e)

        # =======================================
        # LIMPIAR PARA SERIALIZER
        # =======================================
        data = request.data.copy()
        data.pop("foto_perfil", None)
        data.pop("hoja_vida", None)

        serializer = PerfilUsuarioSerializer(perfil, data=data, partial=True)

        if serializer.is_valid():
            serializer.save()
            data = serializer.data
            data.setdefault("telefono", None)
            data.setdefault("documento", None)
            return Response(data, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

     # ========================================
    #                  PATCH
    # ========================================
    def patch(self, request):
        perfil, _ = PerfilUsuario.objects.get_or_create(user=request.user)

        # ==============================
        #       PROCESAR FOTO
        # ==============================
        foto = request.FILES.get("foto_perfil")
        if foto:
            foto_url = _upload_to_cloudinary(
                file_bytes=foto.read(),
                folder=f"perfiles/{request.user.id}/foto",
                filename=foto.name,
                resource_type="image",
            )

            perfil.foto_perfil = foto_url
            perfil.save(update_fields=["foto_perfil"])

        # ==============================
        #     PROCESAR HOJA DE VIDA
        # ==============================
        hoja = request.FILES.get("hoja_vida")
        if hoja:
            cv_url = _upload_to_cloudinary(
                file_bytes=hoja.read(),
                folder=f"perfiles/{request.user.id}/hoja_vida",
                filename=hoja.name,
                resource_type="raw",
            )

            perfil.hoja_vida = cv_url
            perfil.save(update_fields=["hoja_vida"])

        # ==============================
        #  ACTUALIZAR CAMPOS NORMALES
        # ==============================
        data = request.data.copy()
        data.pop("foto_perfil", None)
        data.pop("hoja_vida", None)

        serializer = PerfilUsuarioSerializer(perfil, data=data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=400)


class FavoritosView(APIView):
    permission_classes = [IsAuthenticated, IsAdminOrRRHH, CheckUserInactivityPermission]   # Solo admin y RRHH pueden gestionar favoritos
    # ---------------------------
    # GET → Listar favoritos
    # ---------------------------
    def get(self, request):
        rrhh = request.user.id
        favoritos = Favorito.objects.filter(rrhh_id=rrhh)

        serializer = FavoritoSerializer(favoritos, many=True)
        return Response(serializer.data)

    # ---------------------------
    # POST → Marcar favorito
    # ---------------------------
    def post(self, request):
        rrhh = request.user.id
        candidato_id = request.data.get("candidato_id") or request.data.get("id_candidato")
        postulacion_id = request.data.get("postulacion_id") or request.data.get("id_postulacion")

        if not candidato_id and not postulacion_id:
            return Response(
                {"error": "Debe enviar candidato_id o postulacion_id."},
                status=400,
            )

        if postulacion_id and not candidato_id:
            try:
                postulacion_id = int(postulacion_id)
                if postulacion_id <= 0:
                    raise ValueError()
            except (TypeError, ValueError):
                return Response({"error": "postulacion_id debe ser un entero válido."}, status=400)

            postulacion = Postulacion.objects.filter(id=postulacion_id).select_related("candidato").first()
            if not postulacion or not postulacion.candidato_id:
                return Response({"error": "Postulación no encontrada."}, status=404)
            candidato_id = postulacion.candidato_id

        try:
            candidato_id = int(candidato_id)
            if candidato_id <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            return Response({"error": "candidato_id debe ser un entero válido."}, status=400)

        candidato = User.objects.filter(id=candidato_id).first()
        if not candidato:
            return Response({"error": "Candidato no encontrado."}, status=404)

        candidato_role = normalize_role(getattr(candidato, "role", None) or get_supabase_role(candidato))
        # Solo bloquear roles explícitamente no-candidato para evitar falsos negativos
        # cuando el rol llega nulo o con un valor legacy.
        if candidato_role in (Roles.ADMIN, Roles.EMPLEADO_RRHH):
            return Response(
                {
                    "error": "Solo se pueden marcar usuarios con rol candidato.",
                    "rol_detectado": candidato_role,
                },
                status=400,
            )

        try:
            favorito, creado = Favorito.objects.get_or_create(
                rrhh_id=rrhh,
                candidato_id=candidato_id
            )
        except Exception as e:
            return Response({"error": f"No fue posible guardar el favorito: {str(e)}"}, status=400)

        if not creado:
            return Response({"message": "El candidato ya está marcado como favorito."})

        return Response(FavoritoSerializer(favorito).data, status=201)

    # ---------------------------
    # DELETE → Quitar favorito
    # ---------------------------
    def delete(self, request, candidato_id=None):
        rrhh = request.user.id

        if not candidato_id:
            return Response({"error": "Debe enviar candidato_id en la URL"}, status=400)

        try:
            candidato_id = int(candidato_id)
            if candidato_id <= 0:
                raise ValueError()
        except (TypeError, ValueError):
            return Response({"error": "candidato_id debe ser un entero válido."}, status=400)

        eliminado = Favorito.objects.filter(
            rrhh_id=rrhh,
            candidato_id=candidato_id
        ).delete()

        if eliminado[0] == 0:
            return Response({"error": "Este candidato no estaba en favoritos."}, status=404)

        return Response({"message": "Favorito eliminado correctamente."})

# ----------------------------
# Entrevistas
# ----------------------------
import logging
from datetime import datetime, timedelta
from django.core.mail import EmailMultiAlternatives
logger = logging.getLogger(__name__)

class EntrevistaView(APIView):
    permission_classes = [IsAuthenticated, CheckUserInactivityPermission]

    # ----------------------------
    # Generar archivo .ics
    # ----------------------------
    def generar_ics(self, entrevista):
        start = entrevista.fecha.strftime("%Y%m%d") + "T" + entrevista.hora.strftime("%H%M%S")
        end_dt = datetime.combine(entrevista.fecha, entrevista.hora) + timedelta(hours=1)
        end = end_dt.strftime("%Y%m%dT%H%M%S")

        candidato = entrevista.postulacion.candidato
        correo_candidato = candidato.email

        return f"""BEGIN:VCALENDAR
VERSION:2.0
CALSCALE:GREGORIAN
METHOD:REQUEST
BEGIN:VEVENT
UID:{entrevista.id}@talentohub.com
DTSTAMP:{datetime.now().strftime("%Y%m%dT%H%M%S")}
DTSTART:{start}
DTEND:{end}
SUMMARY:Entrevista – Talento Hub
DESCRIPTION:{entrevista.descripcion}\\nLink: {entrevista.medio}
LOCATION:{entrevista.medio}
ORGANIZER;CN=Talento Hub:mailto:{settings.DEFAULT_FROM_EMAIL}
ATTENDEE;RSVP=TRUE;CN={candidato.first_name}:mailto:{correo_candidato}
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR
"""

    # ----------------------------
    # Enviar correo solo texto (SendGrid)
    # ----------------------------
    def enviar_correo(self, entrevista):
                try:
                        asunto = "Entrevista Programada - Talento Hub"

                        candidato = entrevista.postulacion.candidato
                        correo_destino = candidato.email
                        logo_url = getattr(settings, "TALENTOHUB_LOGO_URL", "")

                        mensaje = f"""
Hola {candidato.first_name},

Tu entrevista ha sido programada exitosamente.

Fecha: {entrevista.fecha}
Hora: {entrevista.hora}
Reunion: {entrevista.medio}

Se adjunta archivo .ics para agregar la entrevista a tu calendario.

Saludos,
Equipo Talento Hub
"""

                        html_logo = f'<img src="{logo_url}" alt="Talento Hub" style="max-height:56px; width:auto; margin-bottom:12px;" />' if logo_url else ""
                        mensaje_html = f"""
<html>
    <body style="font-family: Arial, sans-serif; line-height: 1.6; color: #1f2937; background: #f5f7fb; padding: 24px;">
        <div style="max-width: 640px; margin: 0 auto; background: #ffffff; border: 1px solid #e5e7eb; border-radius: 12px; overflow: hidden;">
            <div style="background: linear-gradient(135deg, #0b5ed7, #0a4eb6); color: #ffffff; padding: 24px; text-align: center;">
                {html_logo}
                <h2 style="margin: 0; font-size: 22px;">Entrevista Programada</h2>
            </div>
            <div style="padding: 24px; color: #374151;">
                <p>Hola <strong>{candidato.first_name or candidato.username}</strong>,</p>
                <p>Tu entrevista ha sido programada exitosamente.</p>
                <div style="background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 16px; margin: 16px 0;">
                    <p style="margin: 0 0 8px 0;"><strong>Fecha:</strong> {entrevista.fecha}</p>
                    <p style="margin: 0 0 8px 0;"><strong>Hora:</strong> {entrevista.hora}</p>
                    <p style="margin: 0;"><strong>Reunion:</strong> <a href="{entrevista.medio}">{entrevista.medio}</a></p>
                </div>
                <p>Adjuntamos un archivo <strong>.ics</strong> para agregar la entrevista a tu calendario.</p>
                <p>Saludos,<br/>Equipo Talento Hub</p>
            </div>
            <div style="padding: 16px 24px; border-top: 1px solid #e5e7eb; color: #6b7280; font-size: 12px; text-align: center;">
                Talento Hub · Gestion de Candidatos
            </div>
        </div>
    </body>
</html>
"""

                        email = EmailMultiAlternatives(
                                subject=asunto,
                                body=mensaje,
                                from_email=settings.DEFAULT_FROM_EMAIL,
                                to=[correo_destino],
                        )
                        email.attach_alternative(mensaje_html, "text/html")

                        archivo_ics = self.generar_ics(entrevista)
                        email.attach("entrevista.ics", archivo_ics, "text/calendar")

                        send_message_async(email)

                except Exception as e:
                        logger.error(f"Error enviando correo async: {e}")
                        print(f"Error enviando correo async: {e}")

    # ----------------------------
    # POST → Crear entrevista
    # ----------------------------
    def post(self, request):
        serializer = EntrevistaSerializer(data=request.data)

        if serializer.is_valid():
            entrevista = serializer.save()

            # Enviar correo automáticamente
            self.enviar_correo(entrevista)

            return Response(serializer.data, status=201)

        return Response(serializer.errors, status=400)


    # ----------------------------
    # GET(por candidato, p)
    # ----------------------------
    def get(self, request, postulacion_id=None, entrevista_id=None, candidato_id=None):

        # Obtener entrevistas por candidato
            if candidato_id:
                postulaciones = Postulacion.objects.filter(candidato_id=candidato_id)
                entrevistas = Entrevista.objects.filter(postulacion__in=postulaciones)
                serializer = EntrevistaSerializer(entrevistas, many=True)
                return Response(serializer.data)

        # Obtener entrevistas por postulación
            if postulacion_id:
                entrevistas = Entrevista.objects.filter(postulacion_id=postulacion_id)
                serializer = EntrevistaSerializer(entrevistas, many=True)
                return Response(serializer.data)

        # Obtener una sola entrevista
            if entrevista_id:
                entrevista = get_object_or_404(Entrevista, id=entrevista_id)
                serializer = EntrevistaSerializer(entrevista)
                return Response(serializer.data)

            return Response({"error": "Debes enviar un identificador"}, status=400)
    
    # ----------------------------
    # PUT
    # ----------------------------
    def put(self, request, entrevista_id):
        entrevista = get_object_or_404(Entrevista, id=entrevista_id)
        serializer = EntrevistaSerializer(entrevista, data=request.data, partial=False)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=400)

    # ----------------------------
    # PATCH
    # ----------------------------
    def patch(self, request, entrevista_id):
        entrevista = get_object_or_404(Entrevista, id=entrevista_id)
        serializer = EntrevistaSerializer(entrevista, data=request.data, partial=True)

        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)

        return Response(serializer.errors, status=400)

    # ----------------------------
    # DELETE
    # ----------------------------
    def delete(self, request, entrevista_id):
        entrevista = get_object_or_404(Entrevista, id=entrevista_id)
        entrevista.delete()
        return Response(status=204)

