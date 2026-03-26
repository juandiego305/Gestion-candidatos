from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_sync_vacante_rrhh_columns"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE core_postulaciones
                ADD COLUMN IF NOT EXISTS id_candidato integer NULL;

                ALTER TABLE core_postulaciones
                ADD COLUMN IF NOT EXISTS id_vacante bigint NULL;

                ALTER TABLE core_postulaciones
                ADD COLUMN IF NOT EXISTS id_empresa bigint NULL;

                DO $$
                BEGIN
                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='core_postulaciones' AND column_name='candidato_id'
                    ) THEN
                        EXECUTE 'UPDATE core_postulaciones SET id_candidato = candidato_id WHERE id_candidato IS NULL';
                    END IF;

                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='core_postulaciones' AND column_name='vacante_id'
                    ) THEN
                        EXECUTE 'UPDATE core_postulaciones SET id_vacante = vacante_id WHERE id_vacante IS NULL';
                    END IF;

                    IF EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name='core_postulaciones' AND column_name='empresa_id'
                    ) THEN
                        EXECUTE 'UPDATE core_postulaciones SET id_empresa = empresa_id WHERE id_empresa IS NULL';
                    END IF;
                END
                $$;

                CREATE INDEX IF NOT EXISTS core_postulaciones_id_candidato_idx
                ON core_postulaciones (id_candidato);

                CREATE INDEX IF NOT EXISTS core_postulaciones_id_vacante_idx
                ON core_postulaciones (id_vacante);

                CREATE INDEX IF NOT EXISTS core_postulaciones_id_empresa_idx
                ON core_postulaciones (id_empresa);

                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'core_postulaciones_id_candidato_fk'
                    ) THEN
                        ALTER TABLE core_postulaciones
                        ADD CONSTRAINT core_postulaciones_id_candidato_fk
                        FOREIGN KEY (id_candidato) REFERENCES auth_user (id)
                        ON DELETE CASCADE;
                    END IF;
                END
                $$;

                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'core_postulaciones_id_vacante_fk'
                    ) THEN
                        ALTER TABLE core_postulaciones
                        ADD CONSTRAINT core_postulaciones_id_vacante_fk
                        FOREIGN KEY (id_vacante) REFERENCES core_vacantes (id)
                        ON DELETE CASCADE;
                    END IF;
                END
                $$;

                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'core_postulaciones_id_empresa_fk'
                    ) THEN
                        ALTER TABLE core_postulaciones
                        ADD CONSTRAINT core_postulaciones_id_empresa_fk
                        FOREIGN KEY (id_empresa) REFERENCES core_empresa (id)
                        ON DELETE CASCADE;
                    END IF;
                END
                $$;
            """,
            reverse_sql="""
                ALTER TABLE core_postulaciones DROP CONSTRAINT IF EXISTS core_postulaciones_id_candidato_fk;
                ALTER TABLE core_postulaciones DROP CONSTRAINT IF EXISTS core_postulaciones_id_vacante_fk;
                ALTER TABLE core_postulaciones DROP CONSTRAINT IF EXISTS core_postulaciones_id_empresa_fk;
                DROP INDEX IF EXISTS core_postulaciones_id_candidato_idx;
                DROP INDEX IF EXISTS core_postulaciones_id_vacante_idx;
                DROP INDEX IF EXISTS core_postulaciones_id_empresa_idx;
                ALTER TABLE core_postulaciones DROP COLUMN IF EXISTS id_candidato;
                ALTER TABLE core_postulaciones DROP COLUMN IF EXISTS id_vacante;
                ALTER TABLE core_postulaciones DROP COLUMN IF EXISTS id_empresa;
            """,
        ),
    ]
