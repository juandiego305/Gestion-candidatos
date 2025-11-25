from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
import os
from django.contrib.auth import get_user_model

User = get_user_model() 

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
# VACANTERRHH
# ────────────────────────────────────────────────
class VacanteRRHH(models.Model):
    # Mapeo explícito a las columnas que existen en la tabla SQL creada por el usuario
    vacante = models.ForeignKey(Vacante, on_delete=models.CASCADE, db_column='vacante_id')
    rrhh_user = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id')  # columna en la BD: user_id
    fecha_asignacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'core_vacante_rrhh'  # nombre real de la tabla creada en la BD
        managed = False                # la tabla ya existe en Supabase/Postgres
        unique_together = ('vacante', 'rrhh_user')  # Garantiza que solo un RRHH esté asignado a una vacante

    def __str__(self):
        return f"RRHH {self.rrhh_user.username} asignado a {self.vacante.titulo}"
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
        db_column="id_candidato",
    )

    vacante = models.ForeignKey(
        Vacante,
        on_delete=models.CASCADE,
        related_name="postulaciones",
        db_column="id_vacante",
    )

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="postulaciones",
        db_column="id_empresa",
    )

    cv_url = models.URLField(null=True, blank=True)
    estado = models.CharField(max_length=50, choices=ESTADOS, default="Postulado")
    fecha_postulacion = models.DateTimeField()

    # ⭐⭐ NUEVO CAMPO PARA GUARDAR COMENTARIOS / CONTACTOS ⭐⭐
    comentarios = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "core_postulaciones"
        managed = False

    def __str__(self):
        return f"{self.candidato.username} - {self.empresa.nombre}"
    

# ────────────────────────────────────────────────
# PERFIL USUARIO - DATOS ADICIONALES
# ────────────────────────────────────────────────

def upload_foto(instance, filename):
    return f"perfiles/{instance.user.id}/foto/{filename}"

def upload_hoja_vida(instance, filename):
    return f"perfiles/{instance.user.id}/hoja_vida/{filename}"

def validate_hoja_vida(file):
    """Validar que el archivo sea .pdf o .docx y no exceda 10MB"""
    # Validar extensión
    ext = os.path.splitext(file.name)[1].lower()
    if ext not in ['.pdf', '.docx']:
        raise ValidationError('Solo se permiten archivos con extensión .pdf o .docx')
    
    # Validar tamaño (10MB = 10485760 bytes)
    if file.size > 10485760:
        raise ValidationError('El archivo no puede exceder 10MB')


# ────────────────────────────────────────────────
# PERFIL USUARIO - DATOS ADICIONALES
# ────────────────────────────────────────────────
    
class PerfilUsuario(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    telefono = models.CharField(max_length=20, blank=True, null=True)
    documento = models.CharField(max_length=50, blank=True, null=True)
    ubicacion = models.CharField(max_length=150, null=True, blank=True)
    descripcion = models.TextField(blank=True, null=True)
    creado = models.DateTimeField(auto_now_add=True)
    actualizado = models.DateTimeField(auto_now=True)
    

    foto_perfil = models.CharField(max_length=500, blank=True, null=True)
    hoja_vida = models.CharField(max_length=500, blank=True, null=True)

    def __str__(self):
        return f"Perfil de {self.user.username}"

      #  return f"{self.candidato.username} - {self.vacante.titulo}"

# ────────────────────────────────────────────────
# FAVORITOS
class Favorito(models.Model):
    rrhh = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column='rrhh_id',
        related_name='favoritos_marcados'
    )
    candidato = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column='candidato_id',
        related_name='favorito_de'
    )
    fecha_marcado = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'core_favoritos'
        managed = False
        unique_together = ('rrhh', 'candidato')

    def __str__(self):
        return f"{self.rrhh.username} → {self.candidato.username}"
    