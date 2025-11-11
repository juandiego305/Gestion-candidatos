# core/serializers_user.py
from django.contrib.auth.models import Group
from rest_framework import serializers
from rest_framework.validators import UniqueValidator
from django.contrib.auth import get_user_model
from core.models import Roles  # 👈 importa desde models.py

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
        user.role = role_name
        user.save()

        group, _ = Group.objects.get_or_create(name=role_name)
        user.groups.add(group)

        print(f"📩 Correo enviado a {user.email}: ¡Bienvenido a la plataforma!")

        return user
    
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    def validate(self, attrs):
        data = super().validate(attrs)
        user = self.user

        groups = [group.name for group in user.groups.all()] if user and user.pk else []

        data.update({
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "role": getattr(user, "role", None),
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
            "role",
            "date_joined",
            "last_login",
        ]
