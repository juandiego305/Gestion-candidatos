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

from core.supabase_client import SUPABASE_URL, get_supabase_client
from core.supabase_client import SUPABASE_SERVICE_KEY

from .serializers_user import PerfilSerializer, UserSerializer
from .models import Empresa, Entrevista, Postulacion, VacanteRRHH

from .serializers_user import PerfilSerializer, UserSerializer, PerfilUsuarioSerializer
from .models import Empresa

from .serializers import EmpresaSerializer, UsuarioSerializer, PostulacionSerializer, EntrevistaSerializer, supabase
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework_simplejwt.views import TokenObtainPairView
from .models import Roles
from supabase import create_client
from rest_framework import generics, permissions

from django.http import JsonResponse
from rest_framework.decorators import api_view
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from .serializers import VacanteSerializer
from datetime import datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from django.shortcuts import get_object_or_404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from .models import Vacante, Postulacion, Empresa
import logging
from .models import Favorito
from .serializers import FavoritoSerializer
from django.db.models import Count, Max
import io
import csv
from io import BytesIO

logger = logging.getLogger(__name__)




supabase = create_client(settings.SUPABASE_URL, settings.SUPABASE_SERVICE_KEY)

def get_supabase_role(user):
    """
    Obtiene el campo 'role' desde la tabla auth_user de Supabase
    usando el id del usuario de Django.
    """
    try:
        # Realiza la consulta en la tabla 'auth_user' en Supabase
        resp = supabase.table("auth_user").select("role").eq("id", user.id).execute()
        
        # Verifica si la respuesta contiene datos
        if resp.data and len(resp.data) > 0:
            role = resp.data[0].get("role")
            print("🔥 Rol desde Supabase:", role)  # Esto te ayudará a depurar el valor de 'role'
            return role
        else:
            print(f"⚠️ Usuario no encontrado en Supabase para id: {user.id}")
            return None
    except Exception as e:
        print(f"⚠️ Error obteniendo rol de Supabase: {e}")
        return None


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
    """Comprueba en Supabase la empresa asociada al usuario.

    Devuelve un int o None.
    """
    try:
        # Priorizar la tabla 'auth_user' (puede contener id_empresa)
        def _parse_value(val):
            if val is None:
                return None
            # Si ya es int
            if isinstance(val, int):
                return val
            # Si es string que contiene dígitos
            if isinstance(val, str):
                s = val.strip()
                if s.isdigit():
                    return int(s)
                # A veces viene como JSON-string o como '{"id": 3}'
                try:
                    import json
                    parsed = json.loads(s)
                    if isinstance(parsed, dict):
                        for k in ("id", "empresa_id", "id_empresa", "company_id", "empresa"):
                            if k in parsed and parsed[k] is not None:
                                try:
                                    return int(parsed[k])
                                except Exception:
                                    pass
                except Exception:
                    pass
                return None
            # Si es dict
            if isinstance(val, dict):
                for k in ("id", "empresa_id", "id_empresa", "company_id", "empresa"):
                    if k in val and val[k] is not None:
                        try:
                            return int(val[k])
                        except Exception:
                            try:
                                return int(str(val[k]))
                            except Exception:
                                return None
            # Otros tipos: intentar convertir a int
            try:
                return int(val)
            except Exception:
                return None

        # 1) Revisar auth_user por id
        try:
            res = supabase.table("auth_user").select("*").eq("id", user.id).execute()
            if res.data:
                row = res.data[0]
                # buscar claves relevantes
                for key in ("id_empresa", "empresa_id", "company_id", "empresa"):
                    if key in row and row.get(key) is not None:
                        parsed = _parse_value(row.get(key))
                        if parsed is not None:
                            logger.debug("Found empresa in auth_user by id: %s -> %s", key, parsed)
                            return parsed
                # si no tiene claves, intentar revisar cualquier campo por si viene embebido
                for k, v in row.items():
                    parsed = _parse_value(v)
                    if parsed is not None:
                        logger.debug("Parsed empresa from auth_user.%s -> %s", k, parsed)
                        return parsed
        except Exception:
            pass

        # 2) Revisar auth_user por email
        try:
            res2 = supabase.table("auth_user").select("*").eq("email", user.email).execute()
            if res2.data:
                row = res2.data[0]
                for key in ("id_empresa", "empresa_id", "company_id", "empresa"):
                    if key in row and row.get(key) is not None:
                        parsed = _parse_value(row.get(key))
                        if parsed is not None:
                            logger.debug("Found empresa in auth_user by email: %s -> %s", key, parsed)
                            return parsed
                for k, v in row.items():
                    parsed = _parse_value(v)
                    if parsed is not None:
                        logger.debug("Parsed empresa from auth_user.%s -> %s", k, parsed)
                        return parsed
        except Exception:
            pass

        # 3) Buscar en 'usuarios' por id
        try:
            res3 = supabase.table("usuarios").select("*").eq("id", user.id).execute()
            if res3.data:
                row = res3.data[0]
                for key in ("empresa_id", "id_empresa", "company_id", "empresa"):
                    if key in row and row.get(key) is not None:
                        parsed = _parse_value(row.get(key))
                        if parsed is not None:
                            logger.debug("Found empresa in usuarios by id: %s -> %s", key, parsed)
                            return parsed
                for k, v in row.items():
                    parsed = _parse_value(v)
                    if parsed is not None:
                        logger.debug("Parsed empresa from usuarios.%s -> %s", k, parsed)
                        return parsed
        except Exception:
            pass

        # 4) Buscar en 'usuarios' por email
        try:
            res4 = supabase.table("usuarios").select("*").eq("email", user.email).execute()
            if res4.data:
                row = res4.data[0]
                for key in ("empresa_id", "id_empresa", "company_id", "empresa"):
                    if key in row and row.get(key) is not None:
                        parsed = _parse_value(row.get(key))
                        if parsed is not None:
                            logger.debug("Found empresa in usuarios by email: %s -> %s", key, parsed)
                            return parsed
                for k, v in row.items():
                    parsed = _parse_value(v)
                    if parsed is not None:
                        logger.debug("Parsed empresa from usuarios.%s -> %s", k, parsed)
                        return parsed
        except Exception:
            pass

    except Exception as e:
        logger.exception("Error leyendo empresa de Supabase para user id=%s: %s", getattr(user, 'id', None), e)
        return None

    return None

from .models import PerfilUsuario, validate_hoja_vida
from rest_framework import status, permissions, parsers 
import time


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

        # --- 3. Buscar usuario por email en Supabase ---
        try:
            resp = supabase.table("auth_user").select("*").eq("email", email).execute()

            if not resp.data:
                return Response(
                    {"error": "No existe un usuario con ese correo."},
                    status=status.HTTP_404_NOT_FOUND
                )

            usuario_supabase = resp.data[0]

        except Exception as e:
            return Response(
                {"error": f"Error consultando Supabase: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )

        empleado_id = usuario_supabase["id"]
        role = usuario_supabase.get("role")
        id_empresa_actual = usuario_supabase.get("id_empresa")

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
            supabase.table("auth_user").update({
                "id_empresa": empresa.id,
                "role": "rrhh"  # convertirlo automáticamente
            }).eq("id", empleado_id).execute()

        except Exception as e:
            return Response(
                {"error": f"Error actualizando Supabase: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
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
@permission_classes([IsAuthenticated])
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

    # 3) Consultar en Supabase los RRHH de esa empresa
    resp = supabase.table("auth_user").select("id, email, role, id_empresa") \
            .eq("id_empresa", empresa_id) \
            .eq("role", "rrhh") \
            .execute()

    trabajadores = resp.data if resp.data else []

    return Response({
        "empresa": empresa.nombre,
        "empresa_id": empresa.id,
        "total_trabajadores": len(trabajadores),
        "trabajadores": trabajadores
    }, status=200)

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def obtener_vacante(request, vacante_id):
    vacante = get_object_or_404(Vacante, id=vacante_id)
    serializer = VacanteSerializer(vacante)
    return Response(serializer.data, status=status.HTTP_200_OK)

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
@permission_classes([IsAuthenticated])
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
@permission_classes([IsAuthenticated])
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

    # 4) Obtener archivo enviado
    archivo_cv = request.FILES.get("cv")
    if not archivo_cv:
        return Response({"error": "Debe adjuntar un archivo 'cv'."}, status=400)

    # Leer bytes del archivo
    contenido = archivo_cv.read()

    # 5) Construir ruta única en Supabase Storage
    ruta_supabase = f"vacantes/{vacante_id}/cv_{request.user.id}.pdf"

    # 6) Subir archivo a Supabase correctamente
    res = supabase.storage.from_("perfiles").upload(
        ruta_supabase,
        contenido,
        file_options={"content-type": archivo_cv.content_type}
    )

    # Validar error del upload
    if res is None or getattr(res, "error", None):
        print("❌ Error subiendo a Supabase:", getattr(res, "error", None))
        return JsonResponse({"error": "Error subiendo archivo a Supabase"}, status=500)

    # 7) Obtener URL pública
    url_final = supabase.storage.from_("perfiles").get_public_url(ruta_supabase)

    # 8) Validar si ya está postulado
    if Postulacion.objects.filter(candidato=request.user, vacante=vacante).exists():
        return JsonResponse({"error": "Ya se encuentra postulado a esta vacante."}, status=400)

    # 9) Crear postulación
    postulacion = Postulacion.objects.create(
        candidato=request.user,
        vacante=vacante,
        empresa=vacante.id_empresa,
        cv_url=url_final,
        estado="Postulado",
        fecha_postulacion=timezone.now()
    )

    # 10) Respuesta final
    return JsonResponse({
        "message": "Postulación registrada correctamente.",
        "postulacion_id": postulacion.id,
        "vacante_id": vacante.id,
        "cv_url": url_final
    }, status=201)

from rest_framework_simplejwt.authentication import JWTAuthentication

@api_view(["GET"])
@permission_classes([IsAuthenticated])
def listar_postulaciones_por_vacante(request, id_vacante):

    # 🔥 Obtener rol e id_empresa directamente desde Supabase
    role = get_supabase_role(request.user)
    id_empresa_usuario = get_supabase_empresa_id(request.user)

    print("🔥 Rol del usuario:", role)
    print("🏭 Empresa del usuario:", id_empresa_usuario)

    vacante = get_object_or_404(Vacante, id=id_vacante)

    if role not in ["rrhh", "admin"]:
        return Response({"detail": "No autorizado"}, status=403)

    if role == "rrhh" and id_empresa_usuario != vacante.id_empresa_id:
        return Response({"detail": "No pertenece a tu empresa"}, status=403)

    postulaciones = Postulacion.objects.filter(vacante_id=id_vacante)
    serializer = PostulacionSerializer(postulaciones, many=True)

    return Response(serializer.data)


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def metrics_dashboard(request):
    """Devuelve métricas agregadas por vacante. Solo admins.

    Filtros por query params:
    - from: ISO date (yyyy-mm-dd) fecha mínima de postulacion
    - to: ISO date fecha máxima
    - area: cadena que filtra `Vacante.ubicacion` (icontains)
    """
    caller_role = normalize_role(getattr(request.user, 'role', None) or get_supabase_role(request.user))
    if caller_role != Roles.ADMIN:
        return Response({'error': 'No autorizado'}, status=403)

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
@permission_classes([IsAuthenticated])
def export_metrics_vacante(request, vacante_id, fmt):
    """Exporta métricas para una vacante dada usando ruta limpia.

    URL: /api/metrics/vacante/<vacante_id>/export/<fmt>/
    fmt: 'csv' | 'excel' | 'pdf'
    Solo administradores pueden usarlo.
    """
    caller_role = normalize_role(getattr(request.user, 'role', None) or get_supabase_role(request.user))
    if caller_role != Roles.ADMIN:
        return Response({'error': 'No autorizado'}, status=403)

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
@permission_classes([IsAuthenticated])
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
@permission_classes([IsAuthenticated])
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

    ESTADOS_VALIDOS = ["Postulado", "En revisión", "Entrevista", "Rechazado", "Contratado"]
    if nuevo_estado not in ESTADOS_VALIDOS:
        return Response({
            "error": f"Estado inválido. Usa uno de: {', '.join(ESTADOS_VALIDOS)}"
        }, status=400)

    postulacion.estado = nuevo_estado
    postulacion.save(update_fields=["estado"])

    return Response({
        "message": "Estado actualizado correctamente",
        "postulacion_id": postulacion.id,
        "nuevo_estado": nuevo_estado
    })
# ----------------------------
# Contactar candidato
# ----------------------------
@api_view(['POST'])
@permission_classes([IsAuthenticated])
def contactar_candidato(request, postulacion_id):
    """
    Endpoint para que el reclutador (RRHH) o admin contacte a un candidato
    y quede registro en la postulación (campo comentarios).
    URL típica: POST /reclutador/postulaciones/<id>/contactar/
    Body (JSON):
    {
        "asunto": "Invitación a entrevista",
        "mensaje": "Hola, hemos revisado tu postulación..."
    }
    """

    # 1️⃣ Verificar rol de quien llama (admin o RRHH)
    caller_role_raw = getattr(request.user, 'role', None) or get_supabase_role(request.user)
    caller_role = normalize_role(caller_role_raw)
    print(f"👤 Caller role raw: {caller_role_raw} -> normalized: {caller_role}")

    if caller_role not in (Roles.ADMIN, Roles.EMPLEADO_RRHH):
        return Response(
            {'error': 'Solo reclutadores (RRHH) o administradores pueden contactar candidatos.'},
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
    asunto = data.get('asunto') or 'Mensaje sobre tu postulación'
    mensaje = data.get('mensaje')

    if not mensaje:
        return Response(
            {'error': 'El campo "mensaje" es obligatorio.'},
            status=400
        )

    destinatario = postulacion.candidato.email

    # 5️⃣ Enviar el correo
    try:
        send_mail(
            subject=asunto,
            message=mensaje,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[destinatario],
            fail_silently=False,
        )
    except Exception as e:
        print("❌ Error enviando correo:", e)
        return Response(
            {'error': f'Error enviando correo: {str(e)}'},
            status=500
        )

    # 6️⃣ Guardar comentario en la postulación (historial)
    marca_tiempo = timezone.now().strftime("%Y-%m-%d %H:%M")
    comentario_nuevo = (
        f"[{marca_tiempo}] {request.user.email} envió correo al candidato:\n"
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

    # 7️⃣ Respuesta
    return Response(
        {'message': f'Correo enviado a {destinatario}'},
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

# Inicializar cliente Supabase con timeout extendido (60s)
import httpx
_timeout = httpx.Timeout(60.0, connect=60.0, read=60.0, write=60.0)
_http_client = httpx.Client(timeout=_timeout, verify=True)

supabase = create_client(
    settings.SUPABASE_URL,
    settings.SUPABASE_SERVICE_KEY,
)

def upload_to_supabase_with_retry(bucket_path, file_bytes, file_name, content_type,
                                  max_retries=3, initial_backoff=1.0):
    """Sube archivos a Supabase con reintentos exponenciales. Recibe bytes directamente."""
    import time as _time
    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            print(f"📤 Intento {attempt}/{max_retries}: subiendo {file_name} ({len(file_bytes)} bytes) a {bucket_path}")
            resp = supabase.storage.from_("perfiles").upload(
                bucket_path,
                file_bytes,
                {"content-type": content_type}
            )
            print(f"✅ Archivo subido exitosamente: {bucket_path}")
            return resp
        except Exception as e:
            last_exc = e
            print(f"⚠️ Error en intento {attempt}: {type(e).__name__}: {e}")
            if attempt == max_retries:
                print(f"❌ Superados {max_retries} intentos para {file_name}")
                raise
            backoff = initial_backoff * (2 ** (attempt - 1))
            print(f"⏳ Esperando {backoff}s antes del siguiente intento...")
            _time.sleep(backoff)
    raise last_exc

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

        # Si no está autenticado, no pasa
        if not user or not user.is_authenticated:
            return False

        # Obtener el rol desde Supabase
        data = supabase.table("auth_user") \
                       .select("role") \
                       .eq("id", user.id) \
                       .execute()

        if not data.data:
            return False

        role = data.data[0]["role"]

        return role in ["admin", "rrhh"]

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
            # Intentar listar buckets
            buckets = supabase.storage.list_buckets()
            bucket_names = [b.name for b in buckets]
            
            return Response({
                "status": "✅ Conectado a Supabase",
                "buckets": bucket_names,
                "perfiles_bucket_exists": "perfiles" in bucket_names
            })
        except Exception as e:
            return Response({
                "status": "❌ Error conectando a Supabase",
                "error": str(e)
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
            user = serializer.create(serializer.validated_data)
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
        1️⃣ Se guarda la empresa con su usuario como owner (lo hace el serializer).
        2️⃣ Se actualiza su rol en Django.
        3️⃣ Se sincroniza el rol y grupo 'admin' en Supabase.
        """
        user = self.request.user

        # 🔹 IMPORTANTE: ya NO pasamos owner=user aquí
        empresa = serializer.save()

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
@permission_classes([IsAuthenticated])
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
    asignacion = VacanteRRHH.objects.create(vacante=vacante, rrhh_user=rrhh_user)

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
        
        response = supabase.table("auth_user").select("*").eq("email", user.email).execute()

        if not response.data:
            return Response({"error": "Usuario no encontrado en Supabase"}, status=404)

        perfil = response.data[0]

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
    permission_classes = [permissions.IsAuthenticated]
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
                path_new = f"{request.user.id}/foto/{int(time.time())}_{foto.name}"
                foto_bytes = foto.read()

                supabase.storage.from_("perfiles").upload(path_new, foto_bytes)

                public_url_resp = supabase.storage.from_("perfiles").get_public_url(path_new)
                public_url = (
                    public_url_resp.get("publicURL")
                    if isinstance(public_url_resp, dict)
                    else public_url_resp
                )

                # Eliminar archivo viejo si existe
                old_photo = perfil.foto_perfil
                if old_photo and isinstance(old_photo, str) and old_photo.startswith(
                    f"{settings.SUPABASE_URL}/storage/v1/object/public/perfiles/"
                ):
                    old_path = old_photo.replace(
                        f"{settings.SUPABASE_URL}/storage/v1/object/public/perfiles/",
                        ""
                    )
                    try:
                        supabase.storage.from_("perfiles").remove([old_path])
                    except:
                        pass

                perfil.foto_perfil = public_url
                perfil.save(update_fields=["foto_perfil"])

            # ======================
            # SUBIR HOJA DE VIDA
            # ======================
            hoja = request.FILES.get("hoja_vida")
            if hoja:
                path = f"{request.user.id}/hoja_vida/{int(time.time())}_{hoja.name}"
                hoja_bytes = hoja.read()

                supabase.storage.from_("perfiles").upload(path, hoja_bytes)

                public_url_resp = supabase.storage.from_("perfiles").get_public_url(path)
                public_url = (
                    public_url_resp.get("publicURL")
                    if isinstance(public_url_resp, dict)
                    else public_url_resp
                )

                # Eliminar anterior
                old_cv = perfil.hoja_vida
                if old_cv and isinstance(old_cv, str) and old_cv.startswith(
                    f"{settings.SUPABASE_URL}/storage/v1/object/public/perfiles/"
                ):
                    old_path = old_cv.replace(
                        f"{settings.SUPABASE_URL}/storage/v1/object/public/perfiles/",
                        ""
                    )
                    try:
                        supabase.storage.from_("perfiles").remove([old_path])
                    except:
                        pass

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
            ext = foto.name.split(".")[-1]
            file_key = f"{request.user.id}/foto/{int(time.time())}.{ext}"

            # Eliminar foto anterior
            old_photo = perfil.foto_perfil
            if old_photo and isinstance(old_photo, str) and "perfiles/" in old_photo:
                old_path = old_photo.split("/public/perfiles/")[-1]
                try:
                    supabase.storage.from_("perfiles").remove([old_path])
                except:
                    pass

            supabase.storage.from_("perfiles").upload(file_key, foto.read())

            foto_url_resp = supabase.storage.from_("perfiles").get_public_url(file_key)
            foto_url = foto_url_resp.get("publicURL") if isinstance(foto_url_resp, dict) else foto_url_resp

            perfil.foto_perfil = foto_url
            perfil.save(update_fields=["foto_perfil"])

        # ==============================
        #     PROCESAR HOJA DE VIDA
        # ==============================
        hoja = request.FILES.get("hoja_vida")
        if hoja:
            ext = hoja.name.split(".")[-1]
            file_key = f"{request.user.id}/hoja_vida/{int(time.time())}.{ext}"

            # Eliminar CV anterior
            old_cv = perfil.hoja_vida
            if old_cv and isinstance(old_cv, str) and "perfiles/" in old_cv:
                old_path = old_cv.split("/public/perfiles/")[-1]
                try:
                    supabase.storage.from_("perfiles").remove([old_path])
                except:
                    pass

            supabase.storage.from_("perfiles").upload(file_key, hoja.read())

            cv_url_resp = supabase.storage.from_("perfiles").get_public_url(file_key)
            cv_url = cv_url_resp.get("publicURL") if isinstance(cv_url_resp, dict) else cv_url_resp

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
    permission_classes = [IsAuthenticated, IsAdminOrRRHH]   # Solo admin y RRHH pueden gestionar favoritos
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
        candidato_id = request.data.get("candidato_id")

        if not candidato_id:
            return Response({"error": "Debe enviar candidato_id"}, status=400)

        favorito, creado = Favorito.objects.get_or_create(
            rrhh_id=rrhh,
            candidato_id=candidato_id
        )

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
class EntrevistaView(APIView):
    permission_classes = [IsAuthenticated]

    # ----------------------------
    # Generar archivo .ics
    # ----------------------------
    def generar_ics(self, entrevista):

        # formatear fecha y hora inicio
        start = entrevista.fecha.strftime("%Y%m%d") + "T" + entrevista.hora.strftime("%H%M%S")

        # duración predeterminada 1 hora
        from datetime import datetime, timedelta
        end_time = datetime.combine(entrevista.fecha, entrevista.hora) + timedelta(hours=1)
        end = end_time.strftime("%Y%m%dT%H%M%S")

        return f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//TalentoHub//ES
CALSCALE:GREGORIAN
METHOD:REQUEST
BEGIN:VEVENT
DTSTART:{start}
DTEND:{end}
SUMMARY:Entrevista – Talento Hub
DESCRIPTION:{entrevista.descripcion}\\nLink reunión: {entrevista.medio}
LOCATION:{entrevista.medio}
STATUS:CONFIRMED
END:VEVENT
END:VCALENDAR
"""

    # ----------------------------
    # Enviar correo
    # ----------------------------
    def enviar_correo(self, entrevista):
        asunto = "Entrevista Programada – Talento Hub"

        mensaje = f"""
Hola {entrevista.postulacion.candidato.first_name},

Tu entrevista ha sido agendada:

📅 Fecha: {entrevista.fecha}
🕒 Hora: {entrevista.hora}
🔗 Reunión: {entrevista.medio}

Adjunto encontrarás la invitación para agregarla a tu Calendar.

Saludos,
Equipo Talento Hub
"""

        # correo del candidato
        correo_destino = entrevista.postulacion.candidato.email

        from django.core.mail import EmailMessage

        email = EmailMessage(
            asunto,
            mensaje,
            "no-reply@talentohub.com",  # cambia si quieres
            [correo_destino]
        )

        # adjuntar archivo ICS
        archivo_ics = self.generar_ics(entrevista)
        email.attach("entrevista.ics", archivo_ics, "text/calendar")

        email.send()

    # ----------------------------
    # GET → listar por postulacion o traer 1 entrevista
    # ----------------------------
    def get(self, request, postulacion_id=None, entrevista_id=None):

        if postulacion_id:
            entrevistas = Entrevista.objects.filter(postulacion_id=postulacion_id)
            serializer = EntrevistaSerializer(entrevistas, many=True)
            return Response(serializer.data)

        entrevista = get_object_or_404(Entrevista, id=entrevista_id)
        serializer = EntrevistaSerializer(entrevista)
        return Response(serializer.data)

    # ----------------------------
    # POST → crear una entrevista (MEJORADO)
    # ----------------------------
    def post(self, request):
        serializer = EntrevistaSerializer(data=request.data)

        if serializer.is_valid():
            entrevista = serializer.save()

            # enviar correo automático
            self.enviar_correo(entrevista)

            return Response(serializer.data, status=201)

        return Response(serializer.errors, status=400)

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
