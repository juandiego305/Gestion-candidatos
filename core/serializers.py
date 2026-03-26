from django.db import IntegrityError, transaction
from django.contrib.auth.models import Group
from django.contrib.auth import get_user_model
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
import cloudinary.uploader
from .models import Entrevista, Favorito, Vacante, Postulacion, Empresa, Roles

User = get_user_model()


ALLOWED_TYPES = {"image/jpeg", "image/png"}


def _upload_logo_to_cloudinary(file_obj, empresa_id: int) -> str:
    """Upload logo file to Cloudinary and return secure URL."""
    original_name = (getattr(file_obj, "name", "logo") or "logo").rsplit(".", 1)[0]
    safe_name = original_name.replace(" ", "_")
    result = cloudinary.uploader.upload(
        file_obj,
        folder=f"empresas/{empresa_id}/logos",
        public_id=safe_name,
        overwrite=True,
        invalidate=True,
        resource_type="image",
    )
    return result.get("secure_url") or result.get("url")


# ─────────────────────────────────────────────────────────────────────────────
# EMPRESAS
# ─────────────────────────────────────────────────────────────────────────────
class EmpresaSerializer(serializers.ModelSerializer):
    nit = serializers.CharField(
        validators=[UniqueValidator(queryset=Empresa.objects.all(), message="NIT ya registrado")]
    )
    logo = serializers.ImageField(write_only=True, required=False)
    logo_url = serializers.CharField(read_only=True)

    class Meta:
        model = Empresa
        fields = ("id", "nombre", "nit", "direccion", "logo_url","descripcion", "logo")

    def validate(self, data):
        creating = self.instance is None
        required_fields = ("nombre", "nit", "direccion")

        if creating:
            for f in required_fields:
                if not data.get(f):
                    raise serializers.ValidationError({f: "Campo obligatorio"})
        else:
            for f in required_fields:
                if f in data and not data.get(f):
                    raise serializers.ValidationError({f: "Campo obligatorio"})

        file = data.get("logo")
        if file:
            if file.size > 5 * 1024 * 1024:
                raise serializers.ValidationError({"logo": "Máx 5 MB"})
            ctype = getattr(file, "content_type", None)
            if ctype and ctype not in ALLOWED_TYPES:
                raise serializers.ValidationError({"logo": "Solo JPG o PNG"})
        return data

    def create(self, validated_data):
        request = self.context["request"]
        file = validated_data.pop("logo", None)

        try:
            with transaction.atomic():
                empresa = Empresa.objects.create(**validated_data, owner=request.user)
        except IntegrityError:
            raise serializers.ValidationError({"nit": "NIT ya registrado"})

        # Subir logo si existe
        if file:
            logo_url = _upload_logo_to_cloudinary(file, empresa.id)
            empresa.logo_url = logo_url
            empresa.save(update_fields=["logo_url"])

        # Cambiar rol del dueño
        user = request.user
       # user.role = "admin"
       # user.save(update_fields=["role"])

        if hasattr(user, "role"):
            user.role = Roles.ADMIN
            user.save(update_fields=["role"])

        # Agregar grupo en Django
        try:
            group, _ = Group.objects.get_or_create(name="Dueño de Empresa")
            user.groups.add(group)
        except Exception:
            pass

        return empresa

    def update(self, instance, validated_data):
        file = validated_data.pop("logo", None)
        for f in ("nombre", "nit", "direccion", "descripcion"):
            if f in validated_data:
                setattr(instance, f, validated_data[f])

        if file:
            instance.logo_url = _upload_logo_to_cloudinary(file, instance.id)

        instance.save()
        return instance

class VacanteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vacante
        fields = ['id', 'titulo', 'descripcion', 'requisitos', 'fecha_expiracion', 'estado', 'id_empresa', 'creado_por']

# ─────────────────────────────────────────────────────────────────────────────
# USUARIOS (Historia de Usuario 2)
# ─────────────────────────────────────────────────────────────────────────────
class UsuarioSerializer(serializers.Serializer):
    email = serializers.EmailField()
    nombre = serializers.CharField(max_length=100)
    rol = serializers.ChoiceField(choices=["Administrador", "Recursos Humanos", "Usuario"])
    #Cambio en ["admin", "reclutador", "candidato"]
    password = serializers.CharField(write_only=True, min_length=8)

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("El correo ya está en uso")
        return value

    def create(self, validated_data):
        email = validated_data["email"]
        nombre = validated_data["nombre"]
        password = validated_data["password"]

        username_base = email.split("@")[0]
        username = username_base
        n = 1
        while User.objects.filter(username=username).exists():
            username = f"{username_base}{n}"
            n += 1

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=nombre,
            is_active=True,
        )

        rol_raw = (validated_data.get("rol") or "").strip().lower()
        role_map = {
            "administrador": Roles.ADMIN,
            "recursos humanos": Roles.EMPLEADO_RRHH,
            "usuario": Roles.CANDIDATO,
        }
        role = role_map.get(rol_raw, Roles.CANDIDATO)
        if hasattr(user, "role"):
            user.role = role
            user.save(update_fields=["role"])

        return {
            "id": user.id,
            "email": user.email,
            "nombre": user.first_name,
            "rol": role,
            "activo": user.is_active,
        }



class PostulacionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Postulacion
        fields = "__all__"


class FavoritoSerializer(serializers.ModelSerializer):
    email_candidato = serializers.SerializerMethodField()
    nombre_candidato = serializers.SerializerMethodField()

    class Meta:
        model = Favorito
        fields = ('id', 'rrhh', 'candidato', 'email_candidato', 'nombre_candidato', 'fecha_marcado')
        read_only_fields = ('fecha_marcado',)

    def get_email_candidato(self, obj):
        candidato = getattr(obj, "candidato", None)
        return getattr(candidato, "email", None)

    def get_nombre_candidato(self, obj):
        candidato = getattr(obj, "candidato", None)
        if not candidato:
            return None
        return f"{candidato.first_name} {candidato.last_name}".strip() or candidato.username
    

class EntrevistaSerializer(serializers.ModelSerializer):
    class Meta:
        model = Entrevista
        fields = [
            "id",
            "postulacion",
            "fecha",
            "hora",
            "medio",
            "valoracion",
            "descripcion",
            "creada_en"
        ]

