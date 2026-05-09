from django.db import models
from django.conf import settings
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db.models import UniqueConstraint
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
            related_name="empresas",
            null=True,
            blank=True,
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
           related_name='vacantes',
           null=True,
           blank=True,
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
           related_name='vacantes_creadas',
           null=True,
           blank=True,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'core_vacantes'   # 👈 nombre EXACTO de la tabla

    def __str__(self):
        return f"Vacante: {self.titulo} - Empresa: {self.id_empresa.nombre}"

# ────────────────────────────────────────────────
# VACANTERRHH
# ────────────────────────────────────────────────
class VacanteRRHH(models.Model):
    # Mapeo explícito a las columnas que existen en la tabla SQL creada por el usuario
    vacante = models.ForeignKey(Vacante, on_delete=models.CASCADE, db_column='vacante_id', null=True, blank=True)
    rrhh_user = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id', null=True, blank=True)  # columna en la BD: user_id
    fecha_asignacion = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'core_vacante_rrhh'  # nombre real de la tabla creada en la BD
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
        null=True,
        blank=True,
    )
    nombre = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        db_table = "core_competencia"  # 👈 Nombre real de la tabla en Supabase

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
        ("Entrevista", "Entrevista"),
        ("Proceso de contratacion", "Proceso de contratacion"),
        ("Contratado", "Contratado"),
    ]

    candidato = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="postulaciones",
        db_column="id_candidato",
            null=True,
            blank=True,
    )

    vacante = models.ForeignKey(
        Vacante,
        on_delete=models.CASCADE,
        related_name="postulaciones",
        db_column="id_vacante",
            null=True,
            blank=True,
    )

    empresa = models.ForeignKey(
        Empresa,
        on_delete=models.CASCADE,
        related_name="postulaciones",
        db_column="id_empresa",
            null=True,
            blank=True,
    )

    cv_url = models.URLField(null=True, blank=True)
    estado = models.CharField(max_length=50, choices=ESTADOS, default="Postulado")
    fecha_postulacion = models.DateTimeField()

    # ⭐⭐ NUEVO CAMPO PARA GUARDAR COMENTARIOS / CONTACTOS ⭐⭐
    comentarios = models.TextField(null=True, blank=True)

    class Meta:
        db_table = "core_postulaciones"

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
           related_name='favoritos_marcados',
        null=True,
        blank=True,
    )
    candidato = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column='candidato_id',
           related_name='favorito_de',
        null=True,
        blank=True,
    )
    fecha_marcado = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'core_favoritos'
        unique_together = ('rrhh', 'candidato')

    def __str__(self):
        return f"{self.rrhh.username} → {self.candidato.username}"
    
# ────────────────────────────────────────────────
# ENTREVISTA
# ────────────────────────────────────────────────
class Entrevista(models.Model):
    postulacion = models.ForeignKey(Postulacion, on_delete=models.CASCADE, related_name="entrevistas")

    fecha = models.DateField()
    hora = models.TimeField()
    medio = models.CharField(max_length=50)  # "Meet", "Teams", "Zoom", "Presencial"
    valoracion = models.IntegerField(null=True, blank=True)  # 1–5
    descripcion = models.TextField(null=True, blank=True)

    creada_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            UniqueConstraint(fields=['fecha', 'hora'], name='unique_entrevista_fecha_hora')
        ]

    def __str__(self):
        return f"Entrevista {self.id} para {self.postulacion}"

    def clean(self):
        """Validaciones:
        - La fecha+hora debe ser en el futuro
        - No debe existir otra entrevista en la misma fecha y hora
        """
        # Combinar fecha y hora en un datetime
        from datetime import datetime
        try:
            dt = datetime.combine(self.fecha, self.hora)
        except Exception:
            raise ValidationError('Fecha u hora inválida')

        # Convertir a aware si es necesario
        try:
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt)
        except Exception:
            # Si USE_TZ está desactivado, timezone.make_aware puede fallar; en ese caso comparamos naive
            pass

        now = timezone.now()
        if dt <= now:
            raise ValidationError('La fecha y hora de la entrevista deben ser en el futuro.')

        # Verificar conflictos (otro registro con misma fecha y hora)
        qs = Entrevista.objects.filter(fecha=self.fecha, hora=self.hora)
        if self.pk:
            qs = qs.exclude(pk=self.pk)
        if qs.exists():
            raise ValidationError('Ya existe una entrevista programada en esa fecha y hora.')

    def save(self, *args, **kwargs):
        # Ejecutar validaciones antes de guardar
        self.full_clean()
        super().save(*args, **kwargs)
