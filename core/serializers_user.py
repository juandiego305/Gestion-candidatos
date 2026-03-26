# core/serializers_user.py
from django.contrib.auth.models import Group
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from django.contrib.auth import get_user_model
from core.models import Roles  # 👈 importa desde models.py
from .models import PerfilUsuario

User = get_user_model()

class UserSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        validators=[UniqueValidator(queryset=User.objects.all(), message="El correo ya está en uso")]
    )
    password = serializers.CharField(write_only=True, min_length=6)
    role = serializers.ChoiceField(choices=Roles.CHOICES, required=False, default=Roles.CANDIDATO)

    class Meta:
        model = User
        fields = ("id", "username", "email", "password", "first_name", "last_name", "role")

    def create(self, validated_data):
        role_name = validated_data.pop("role", Roles.CANDIDATO)
        password = validated_data.pop("password")

        user = User(**validated_data)
        user.set_password(password)
        user.is_active = True
        user.save()

        # Guardar el role correctamente en auth_user (usando raw SQL porque Django no reconoce el campo role)
        from django.db import connection
        try:
            with connection.cursor() as cursor:
                cursor.execute('UPDATE auth_user SET role = %s WHERE id = %s', [role_name, user.id])
        except Exception as e:
            print(f"⚠️ Error al guardar el role: {str(e)}")

        group, _ = Group.objects.get_or_create(name=role_name)
        user.groups.add(group)

        print(f"✅ Usuario {user.email} registrado con rol '{role_name}' correctamente")

        return user
    
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user

        groups = [group.name for group in user.groups.all()] if user and user.pk else []

        # Obtener role directamente de la BD (campo en auth_user, no en modelo Django)
        from django.db import connection
        role = Roles.CANDIDATO
        try:
            with connection.cursor() as cursor:
                cursor.execute('SELECT role FROM auth_user WHERE id = %s', [user.id])
                row = cursor.fetchone()
                if row and row[0]:
                    role = row[0]
        except Exception:
            pass

        data.update({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": role,
            "groups": groups,
        })

        return data
    

class PerfilSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "date_joined",
            "last_login",
        ]
        read_only_fields = ["email"]  



class PerfilUsuarioSerializer(serializers.ModelSerializer):
    class Meta:
        model = PerfilUsuario
        fields = [
            "id",
            "foto_perfil",     # ahora guardará la URL real
            "hoja_vida",
            "telefono",
            "documento",
            "descripcion",
            "ubicacion",
        ]
        read_only_fields = ["id"]
