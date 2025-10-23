# core/serializers_user.py

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework import serializers
from rest_framework.validators import UniqueValidator

# 🔹 Usar el modelo de usuario personalizado configurado en settings.AUTH_USER_MODEL
User = get_user_model()


class UserSerializer(serializers.ModelSerializer):
    email = serializers.EmailField(
        validators=[
            UniqueValidator(
                queryset=User.objects.all(),
                message="El correo ya está en uso"
            )
        ]
    )
    password = serializers.CharField(write_only=True, min_length=6)
    role = serializers.CharField(write_only=True, required=False)  # rol opcional (grupo)

    class Meta:
        model = User
        fields = (
            "id",
            "username",
            "email",
            "password",
            "first_name",
            "last_name",
            "role",
        )

    def create(self, validated_data):
        role_name = validated_data.pop("role", None)
        password = validated_data.pop("password")

        # Crear el usuario usando el modelo personalizado
        user = User(**validated_data)
        user.set_password(password)
        user.is_active = True
        user.save()

        # Asignar grupo (rol)
        if role_name:
            group, _ = Group.objects.get_or_create(name=role_name)
            user.groups.add(group)

        # Simular envío de correo (puedes reemplazar por lógica real después)
        print(f"📩 Correo enviado a {user.email}: ¡Bienvenido a la plataforma!")

        return user

