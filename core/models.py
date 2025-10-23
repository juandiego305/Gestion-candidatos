from django.db import models
from django.conf import settings
from django.contrib.auth.models import AbstractUser

class Empresa(models.Model):
    nombre = models.CharField(max_length=160)
    nit = models.CharField(max_length=30, unique=True, db_index=True)
    direccion = models.CharField(max_length=200)
    logo_url = models.URLField(blank=True)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="empresas")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre} ({self.nit})"

class Usuario(AbstractUser):
    ROL_CHOICES = [
        ('admin', 'Administrador'),
        ('reclutador', 'Reclutador'),
        ('candidato', 'Candidato'),
    ]
    rol = models.CharField(max_length=20, choices=ROL_CHOICES, default='candidato')

    def __str__(self):
        return f"{self.username} ({self.get_rol_display()})"

class Vacante(models.Model):
    id_empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="vacantes")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Vacante {self.id} - Empresa {self.id_empresa.nombre}"


class Competencia(models.Model):
    id_vacante = models.ForeignKey(Vacante, on_delete=models.CASCADE, related_name="competencias")
    nombre = models.CharField(max_length=100, null=True, blank=True)

    def __str__(self):
        return self.nombre or f"Competencia {self.id}"


class Postulacion(models.Model):
    fecha_postulacion = models.DateTimeField(auto_now_add=True)
    estado = models.CharField(max_length=50)
    candidato = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="postulaciones")
    empresa = models.ForeignKey(Empresa, on_delete=models.CASCADE, related_name="postulaciones")

    def __str__(self):
        return f"{self.candidato.username} - {self.empresa.nombre}"
