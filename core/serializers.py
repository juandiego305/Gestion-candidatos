from urllib.parse import urlparse
from django.db import IntegrityError, transaction
from django.contrib.auth.models import Group
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from .supabase_client import supabase
from .models import Favorito, Vacante, Postulacion, Empresa


ALLOWED_TYPES = {"image/jpeg", "image/png"}


def _storage_key_from_public_url(public_url: str) -> str | None:
    if not public_url:
        return None
    try:
        path = urlparse(public_url).path
        marker = "/storage/v1/object/public/logos/"
        i = path.find(marker)
        if i == -1:
            return None
        return path[i + len(marker):]
    except Exception:
        return None


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
            path = f"{empresa.id}/{file.name}"
            supabase.storage.from_("logos").upload(
                path, file.read(), {"content-type": getattr(file, "content_type", "image/png")}
            )
            empresa.logo_url = supabase.storage.from_("logos").get_public_url(path)
            empresa.save(update_fields=["logo_url"])

        # Cambiar rol del dueño
        user = request.user
       # user.role = "admin"
       # user.save(update_fields=["role"])

        # Actualizar en Supabase
        try:
            supabase.table("auth_user").update({
                "role": "admin"
            }).eq("email", user.email).execute()
        except Exception as e:
            print(f"⚠️ No se pudo actualizar el rol en Supabase: {e}")

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
            old_key = _storage_key_from_public_url(instance.logo_url or "")
            if old_key:
                try:
                    supabase.storage.from_("logos").remove([old_key])
                except Exception:
                    pass
            path = f"{instance.id}/{file.name}"
            supabase.storage.from_("logos").upload(
                path, file.read(), {"content-type": getattr(file, "content_type", "image/png")}
            )
            instance.logo_url = supabase.storage.from_("logos").get_public_url(path)

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
        # Verificar si el correo ya existe en la tabla de Supabase
        response = supabase.table("usuarios").select("id").eq("email", value).execute()
        if response.data:
            raise serializers.ValidationError("El correo ya está en uso")
        return value

    def create(self, validated_data):
        """
        Crea el usuario en Supabase (autenticación + tabla de usuarios)
        """
        # 1️⃣ Crear el usuario en Supabase Auth
        try:
            auth_response = supabase.auth.sign_up({
                "email": validated_data["email"],
                "password": validated_data["password"]
            })
        except Exception as e:
            raise serializers.ValidationError({"auth": f"Error al registrar el usuario: {e}"})

        if not getattr(auth_response, "user", None):
            raise serializers.ValidationError({"auth": "No se pudo crear el usuario en Supabase Auth"})

        user_id = auth_response.user.id

        # 2️⃣ Guardar datos adicionales en la tabla "usuarios"
        response = supabase.table("usuarios").insert({
            "id": user_id,
            "email": validated_data["email"],
            "nombre": validated_data["nombre"],
            "rol": validated_data["rol"],
            "activo": True,
        }).execute()

        if not response.data:
            raise serializers.ValidationError("Error al registrar los datos del usuario en la base de datos")

        return response.data[0]



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
        return obj.candidato.email

    def get_nombre_candidato(self, obj):
        return f"{obj.candidato.first_name} {obj.candidato.last_name}".strip()
