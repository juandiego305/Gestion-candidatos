from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_add_user_fields"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE core_vacantes
                ADD COLUMN IF NOT EXISTS id_empresa bigint NULL;

                ALTER TABLE core_vacantes
                ADD COLUMN IF NOT EXISTS creado_por_id integer NULL;

                CREATE INDEX IF NOT EXISTS core_vacantes_id_empresa_idx
                ON core_vacantes (id_empresa);

                CREATE INDEX IF NOT EXISTS core_vacantes_creado_por_id_idx
                ON core_vacantes (creado_por_id);

                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'core_vacantes_id_empresa_fk'
                    ) THEN
                        ALTER TABLE core_vacantes
                        ADD CONSTRAINT core_vacantes_id_empresa_fk
                        FOREIGN KEY (id_empresa) REFERENCES core_empresa (id)
                        ON DELETE CASCADE;
                    END IF;
                END
                $$;

                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'core_vacantes_creado_por_fk'
                    ) THEN
                        ALTER TABLE core_vacantes
                        ADD CONSTRAINT core_vacantes_creado_por_fk
                        FOREIGN KEY (creado_por_id) REFERENCES auth_user (id)
                        ON DELETE CASCADE;
                    END IF;
                END
                $$;
            """,
            reverse_sql="""
                ALTER TABLE core_vacantes DROP CONSTRAINT IF EXISTS core_vacantes_id_empresa_fk;
                ALTER TABLE core_vacantes DROP CONSTRAINT IF EXISTS core_vacantes_creado_por_fk;
                DROP INDEX IF EXISTS core_vacantes_id_empresa_idx;
                DROP INDEX IF EXISTS core_vacantes_creado_por_id_idx;
                ALTER TABLE core_vacantes DROP COLUMN IF EXISTS id_empresa;
                ALTER TABLE core_vacantes DROP COLUMN IF EXISTS creado_por_id;
            """,
        )
    ]
