import os
import sys
import time

import psycopg2
from psycopg2 import sql


def _env(name, default):
    return str(os.getenv(name, default) or default).strip()


def main():
    db_name = _env("POSTGRES_DB", "product_db")
    user = _env("POSTGRES_USER", "postgres")
    password = _env("POSTGRES_PASSWORD", "postgres")
    host = _env("POSTGRES_HOST", "postgres")
    port = _env("POSTGRES_PORT", "5432")
    max_attempts = max(1, int(_env("POSTGRES_BOOTSTRAP_MAX_ATTEMPTS", "30")))
    sleep_seconds = max(1, int(_env("POSTGRES_BOOTSTRAP_SLEEP_SECONDS", "2")))

    for attempt in range(1, max_attempts + 1):
        try:
            connection = psycopg2.connect(
                dbname="postgres",
                user=user,
                password=password,
                host=host,
                port=port,
                connect_timeout=5,
            )
            connection.autocommit = True
            try:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT 1 FROM pg_database WHERE datname = %s", [db_name])
                    exists = cursor.fetchone() is not None
                    if not exists:
                        cursor.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db_name)))
                        print(f"[bootstrap_postgres] Created database '{db_name}'.")
                    else:
                        print(f"[bootstrap_postgres] Database '{db_name}' already exists.")
                return 0
            finally:
                connection.close()
        except psycopg2.Error as exc:
            print(
                f"[bootstrap_postgres] Attempt {attempt}/{max_attempts} failed: {exc}",
                file=sys.stderr,
            )
            if attempt == max_attempts:
                return 1
            time.sleep(sleep_seconds)

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
