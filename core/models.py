from django.db import models
from django.conf import settings
from django.db import models
# from django.contrib.auth.models import AbstractUser
from django.db import models

class Roles:
    ADMIN = "admin"
    EMPLEADO_RRHH = "empleado_rrhh"
    CANDIDATO = "candidato"

    CHOICES = [
        (ADMIN, "Admin / Dueño de empresa"),
        (EMPLEADO_RRHH, "Empleado / RRHH"),
        (CANDIDATO, "Candidato"),
    ]


   
# ────────────────────────────────────────────────
# EMPRESA
# ────────────────────────────────────────────────
class Empresa(models.Model):
    nombre = models.CharField(max_length=160)
    nit = models.CharField(max_length=30, unique=True, db_index=True)
    direccion = models.CharField(max_length=200)
    logo_url = models.URLField(blank=True)
    # Usa el usuario por defecto de Django (auth_user)
    descripcion = models.TextField(null=True, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="empresas"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.nombre} ({self.nit})"


# ────────────────────────────────────────────────
# VACANTE
# ────────────────────────────────────────────────

class Vacante(models.Model):
    ESTADOS = [
        ('Borrador', 'Borrador'),
        ('Publicado', 'Publicado'),
    ]

    MODALIDADES = [
        ('Hibrido', 'Híbrido'),
        ('Remoto', 'Remoto'),
        ('Presencial', 'Presencial'),
    ]

    id_empresa = models.ForeignKey(
        'core.Empresa',
        on_delete=models.CASCADE,
        db_column='id_empresa',
        related_name='vacantes'
    )
    titulo = models.CharField(max_length=200)
    descripcion = models.TextField()
    requisitos = models.TextField()
    fecha_expiracion = models.DateTimeField()
    estado = models.CharField(max_length=20, choices=ESTADOS, default='Borrador')
    ubicacion = models.CharField(max_length=255, null=True, blank=True)
    salario = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    experiencia = models.CharField(max_length=255, null=True, blank=True)
    beneficios = models.TextField(null=True, blank=True)
    tipo_jornada = models.CharField(max_length=50, null=True, blank=True)
    modalidad_trabajo = models.CharField(
        max_length=20,
        choices=MODALIDADES,
        null=True,
        blank=True,
    )

    # la columna en Supabase se llama creado_por_id
    creado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        db_column='creado_por_id',
        related_name='vacantes_creadas'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_vacantes'   # 👈 nombre EXACTO de la tabla
        managed = False              # 👈 no tocará la tabla con migraciones

    def __str__(self):
        return f"Vacante: {self.titulo} - Empresa: {self.id_empresa.nombre}"


# ────────────────────────────────────────────────
# COMPETENCIA
# ────────────────────────────────────────────────
class Competencia(models.Model):
    id_vacante = models.ForeignKey(
        Vacante,
        on_delete=models.CASCADE,
        related_name="competencias",
        db_column="id_vacante",   # 👈 MUY IMPORTANTE
    )
    nombre = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = "core_competencia"  # 👈 Nombre real de la tabla en Supabase
        managed = False                # 👈 Para que Django NO intente crear/alterar esta tabla

    def __str__(self):
        return self.nombre or f"Competencia {self.id}"


# ────────────────────────────────────────────────
# POSTULACIÓN
# ────────────────────────────────────────────────
class Postulacion(models.Model):
    ESTADOS = [
        ("Postulado", "Postulado"),
        ("En revisión", "En revisión"),
        ("Rechazado", "Rechazado"),
        ("Aceptado", "Aceptado"),
    ]

    candidato = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="postulaciones",
        db_column="candidato_id",   # columna real en la BD
    )

    vacante = models.ForeignKey(
        Vacante,
        on_delete=models.CASCADE,
        related_name="postulaciones",
        db_column="id_vacante",     # 👈 coincide con el CREATE TABLE
    )

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="postulaciones",
        db_column="empresa_id",
    )

    cv_url = models.URLField(null=True, blank=True)
    estado = models.CharField(max_length=50, choices=ESTADOS, default="Postulado")
    fecha_postulacion = models.DateTimeField()

    class Meta:
        db_table = "core_postulaciones"  # 👈 nombre exacto de la tabla
        managed = False                  # 👈 Django NO crea/borra esta tabla

    def __str__(self):
        return f"{self.candidato.username} - {self.vacante.titulo}"
