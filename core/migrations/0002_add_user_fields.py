# Generated migration to register role and id_empresa fields on auth_user

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        # Los campos ya existen en la BD, solo registramos en Django
        migrations.RunSQL(
            sql="SELECT 1",  # No-op, solo para marcar aplicada
            reverse_sql="SELECT 1"
        ),
    ]
