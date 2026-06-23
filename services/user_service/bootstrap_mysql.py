import os
import sys
import time

import pymysql


def _env(name, default):
    return str(os.getenv(name, default) or default).strip()


def _quote_identifier(value):
    return f"`{str(value).replace('`', '``')}`"


def _quote_literal(value):
    return "'" + str(value).replace("\\", "\\\\").replace("'", "\\'") + "'"


def _ensure_database_and_user(db_name, user, password, host, port):
    root_password = _env("MYSQL_ROOT_PASSWORD", "root_password")
    connection = pymysql.connect(
        host=host,
        port=port,
        user="root",
        password=root_password,
        charset="utf8mb4",
        connect_timeout=5,
        read_timeout=5,
        write_timeout=5,
        autocommit=True,
    )
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {_quote_identifier(db_name)}")
            cursor.execute(
                f"CREATE USER IF NOT EXISTS {_quote_literal(user)}@'%' IDENTIFIED BY {_quote_literal(password)}"
            )
            cursor.execute(
                f"ALTER USER {_quote_literal(user)}@'%' IDENTIFIED BY {_quote_literal(password)}"
            )
            cursor.execute(
                f"GRANT ALL PRIVILEGES ON {_quote_identifier(db_name)}.* TO {_quote_literal(user)}@'%'"
            )
            cursor.execute(
                f"GRANT ALL PRIVILEGES ON `test\\_%`.* TO {_quote_literal(user)}@'%'"
            )
            cursor.execute(
                f"GRANT CREATE, DROP ON *.* TO {_quote_literal(user)}@'%'"
            )
            cursor.execute("FLUSH PRIVILEGES")
    finally:
        connection.close()


def main():
    db_name = _env("MYSQL_DATABASE", "user_db")
    user = _env("MYSQL_USER", "user_user")
    password = _env("MYSQL_PASSWORD", "user_password")
    host = _env("MYSQL_HOST", "mysql")
    port = max(1, int(_env("MYSQL_PORT", "3306")))
    max_attempts = max(1, int(_env("MYSQL_BOOTSTRAP_MAX_ATTEMPTS", "30")))
    sleep_seconds = max(1, int(_env("MYSQL_BOOTSTRAP_SLEEP_SECONDS", "2")))

    for attempt in range(1, max_attempts + 1):
        connection = None
        try:
            connection = pymysql.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=db_name,
                charset="utf8mb4",
                connect_timeout=5,
                read_timeout=5,
                write_timeout=5,
                autocommit=True,
            )
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            _ensure_database_and_user(db_name, user, password, host, port)
            print(f"[bootstrap_mysql] MySQL is ready for database '{db_name}'.")
            return 0
        except pymysql.MySQLError as exc:
            if getattr(exc, "args", None) and exc.args[0] in {1044, 1045, 1049}:
                try:
                    _ensure_database_and_user(db_name, user, password, host, port)
                    print(
                        f"[bootstrap_mysql] Ensured database/user for '{db_name}' and will retry.",
                        file=sys.stderr,
                    )
                except pymysql.MySQLError as bootstrap_exc:
                    print(
                        f"[bootstrap_mysql] Bootstrap failed while ensuring '{db_name}': {bootstrap_exc}",
                        file=sys.stderr,
                    )
            print(
                f"[bootstrap_mysql] Attempt {attempt}/{max_attempts} failed: {exc}",
                file=sys.stderr,
            )
            if attempt == max_attempts:
                return 1
            time.sleep(sleep_seconds)
        finally:
            if connection is not None:
                connection.close()

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
