from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_sync_vacante_fk_columns"),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE core_vacante_rrhh
                ADD COLUMN IF NOT EXISTS vacante_id bigint NULL;

                ALTER TABLE core_vacante_rrhh
                ADD COLUMN IF NOT EXISTS user_id integer NULL;

                CREATE INDEX IF NOT EXISTS core_vacante_rrhh_vacante_id_idx
                ON core_vacante_rrhh (vacante_id);

                CREATE INDEX IF NOT EXISTS core_vacante_rrhh_user_id_idx
                ON core_vacante_rrhh (user_id);

                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'core_vacante_rrhh_vacante_fk'
                    ) THEN
                        ALTER TABLE core_vacante_rrhh
                        ADD CONSTRAINT core_vacante_rrhh_vacante_fk
                        FOREIGN KEY (vacante_id) REFERENCES core_vacantes (id)
                        ON DELETE CASCADE;
                    END IF;
                END
                $$;

                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM pg_constraint
                        WHERE conname = 'core_vacante_rrhh_user_fk'
                    ) THEN
                        ALTER TABLE core_vacante_rrhh
                        ADD CONSTRAINT core_vacante_rrhh_user_fk
                        FOREIGN KEY (user_id) REFERENCES auth_user (id)
                        ON DELETE CASCADE;
                    END IF;
                END
                $$;

                CREATE UNIQUE INDEX IF NOT EXISTS core_vacante_rrhh_unique_idx
                ON core_vacante_rrhh (vacante_id, user_id);
            """,
            reverse_sql="""
                DROP INDEX IF EXISTS core_vacante_rrhh_unique_idx;
                ALTER TABLE core_vacante_rrhh DROP CONSTRAINT IF EXISTS core_vacante_rrhh_vacante_fk;
                ALTER TABLE core_vacante_rrhh DROP CONSTRAINT IF EXISTS core_vacante_rrhh_user_fk;
                DROP INDEX IF EXISTS core_vacante_rrhh_vacante_id_idx;
                DROP INDEX IF EXISTS core_vacante_rrhh_user_id_idx;
                ALTER TABLE core_vacante_rrhh DROP COLUMN IF EXISTS vacante_id;
                ALTER TABLE core_vacante_rrhh DROP COLUMN IF EXISTS user_id;
            """,
        ),
    ]
