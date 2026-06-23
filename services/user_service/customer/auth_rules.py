ROLE_ADMIN = "admin"
ROLE_STAFF = "staff"
ROLE_CUSTOMER = "customer"


def resolve_primary_role(*, is_staff=False, is_superuser=False):
    if is_superuser:
        return ROLE_ADMIN
    if is_staff:
        return ROLE_STAFF
    return ROLE_CUSTOMER


def role_scopes_from_sources(*, source_names=(), is_staff=False, is_superuser=False):
    if is_superuser:
        return [ROLE_ADMIN]

    normalized_sources = {str(source).strip().lower() for source in source_names if source}
    scopes = []
    if ROLE_CUSTOMER in normalized_sources or not is_staff:
        scopes.append(ROLE_CUSTOMER)
    if ROLE_STAFF in normalized_sources or is_staff:
        scopes.append(ROLE_STAFF)
    return scopes or [ROLE_CUSTOMER]


def can_access_customer(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and not getattr(user, "is_staff", False)
        and not getattr(user, "is_superuser", False)
    )


def can_access_staff(user):
    return bool(
        getattr(user, "is_authenticated", False)
        and getattr(user, "is_staff", False)
        and not getattr(user, "is_superuser", False)
    )
