"""Single-owner authentication and database query privilege boundaries."""
import base64
import secrets
from fastapi.responses import JSONResponse
from backend.config import get_settings


def validate_deployment():
    settings = get_settings()
    if settings.app_env.lower() == "production":
        if len(settings.app_password) < 16 or not settings.database_query_role:
            raise RuntimeError("Production requires APP_PASSWORD (at least 16 characters) and DATABASE_QUERY_ROLE (a restricted PostgreSQL role).")


async def authenticate(request, call_next):
    settings = get_settings()
    if settings.app_password:
        header = request.headers.get("authorization", "")
        valid = False
        try:
            scheme, encoded = header.split(" ", 1)
            user, password = base64.b64decode(encoded, validate=True).decode().split(":", 1)
            valid = scheme.lower() == "basic" and secrets.compare_digest(user.encode(), settings.app_username.encode()) and secrets.compare_digest(password.encode(), settings.app_password.encode())
        except (ValueError, UnicodeError):
            pass
        if not valid:
            return JSONResponse({"detail": "Authentication required."}, 401, headers={"WWW-Authenticate": 'Basic realm="Data Analyst", charset="UTF-8"'})
    return await call_next(request)


def restrict_query_connection(conn):
    role = get_settings().database_query_role
    if role:
        quoted = '"' + role.replace('"', '""') + '"'
        conn.exec_driver_sql(f"SET LOCAL ROLE {quoted}")
        unsafe = conn.exec_driver_sql("SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls FROM pg_roles WHERE rolname=current_user").scalar()
        if unsafe:
            raise RuntimeError("The query role must not have administrative privileges.")
