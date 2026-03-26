from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_sync_postulacion_fk_columns"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE core_favoritos
                ADD COLUMN IF NOT EXISTS rrhh_id integer NULL;

                ALTER TABLE core_favoritos
                ADD COLUMN IF NOT EXISTS candidato_id integer NULL;

                CREATE INDEX IF NOT EXISTS core_favoritos_rrhh_id_idx
                ON core_favoritos (rrhh_id);

                CREATE INDEX IF NOT EXISTS core_favoritos_candidato_id_idx
                ON core_favoritos (candidato_id);

                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'core_favoritos_rrhh_fk'
                    ) THEN
                        ALTER TABLE core_favoritos
                        ADD CONSTRAINT core_favoritos_rrhh_fk
                        FOREIGN KEY (rrhh_id) REFERENCES auth_user (id)
                        ON DELETE CASCADE;
                    END IF;
                END
                $$;

                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'core_favoritos_candidato_fk'
                    ) THEN
                        ALTER TABLE core_favoritos
                        ADD CONSTRAINT core_favoritos_candidato_fk
                        FOREIGN KEY (candidato_id) REFERENCES auth_user (id)
                        ON DELETE CASCADE;
                    END IF;
                END
                $$;

                CREATE UNIQUE INDEX IF NOT EXISTS core_favoritos_unique_idx
                ON core_favoritos (rrhh_id, candidato_id);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS core_favoritos_unique_idx;
                ALTER TABLE core_favoritos DROP CONSTRAINT IF EXISTS core_favoritos_rrhh_fk;
                ALTER TABLE core_favoritos DROP CONSTRAINT IF EXISTS core_favoritos_candidato_fk;
                DROP INDEX IF EXISTS core_favoritos_rrhh_id_idx;
                DROP INDEX IF EXISTS core_favoritos_candidato_id_idx;
                ALTER TABLE core_favoritos DROP COLUMN IF EXISTS rrhh_id;
                ALTER TABLE core_favoritos DROP COLUMN IF EXISTS candidato_id;
            """,
        ),
    ]
