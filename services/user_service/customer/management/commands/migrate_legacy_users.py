import pymysql
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from customer.legacy_users import format_account_report, merge_legacy_accounts
from customer.models import LegacyUserMapping

User = get_user_model()


def _mysql_connection(database_name):
    default_db = settings.DATABASES["default"]
    return pymysql.connect(
        host=default_db["HOST"],
        port=int(default_db["PORT"]),
        user=default_db["USER"],
        password=default_db["PASSWORD"],
        database=database_name,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def _fetch_legacy_users(database_name, source_name):
    with _mysql_connection(database_name) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT id, username, email, password, first_name, last_name, is_staff, is_superuser
                FROM auth_user
                ORDER BY id ASC
                """
            )
            rows = cursor.fetchall()
    for row in rows:
        row["source"] = source_name
    return rows


def _find_existing_user(account):
    if account["email"]:
        lookup = User.objects.filter(email__iexact=account["email"]).order_by("id").first()
        if lookup is not None:
            return lookup, "email"
    if account["username"]:
        lookup = User.objects.filter(username__iexact=account["username"]).order_by("id").first()
        if lookup is not None:
            return lookup, "username"
    return None, None


def _find_field_collision(field_name, value, *, exclude_user_id):
    if not value:
        return None
    lookup_key = f"{field_name}__iexact" if field_name in {"username", "email"} else field_name
    return User.objects.filter(**{lookup_key: value}).exclude(pk=exclude_user_id).order_by("id").first()


def _sync_account_to_user(user, account):
    sync_notes = []
    update_fields = []

    def _maybe_update(field_name, value):
        if value in [None, ""]:
            return

        current = getattr(user, field_name)
        if field_name in {"username", "email"}:
            collision = _find_field_collision(field_name, value, exclude_user_id=user.pk)
            if collision is not None:
                sync_notes.append(
                    f"{field_name} collision in shared auth: kept '{current}', ignored '{value}' because "
                    f"user #{collision.pk} already uses it."
                )
                return
            current_normalized = str(current or "").strip().lower()
            incoming_normalized = str(value).strip().lower()
            if current_normalized == incoming_normalized:
                return
        elif current == value:
            return

        setattr(user, field_name, value)
        update_fields.append(field_name)

    _maybe_update("username", account["username"])
    _maybe_update("email", account["email"])
    _maybe_update("password", account["password"])
    _maybe_update("first_name", account["first_name"])
    _maybe_update("last_name", account["last_name"])

    merged_is_superuser = bool(user.is_superuser or account["is_superuser"])
    merged_is_staff = bool(user.is_staff or account["is_staff"] or merged_is_superuser)
    if user.is_superuser != merged_is_superuser:
        user.is_superuser = merged_is_superuser
        update_fields.append("is_superuser")
    if user.is_staff != merged_is_staff:
        user.is_staff = merged_is_staff
        update_fields.append("is_staff")

    if update_fields:
        user.save(update_fields=sorted(set(update_fields)))

    return sync_notes


def _build_mapping_note(account, *, action, existing_match, sync_notes):
    lines = [
        f"action={action}",
        f"existing_match={existing_match or 'created'}",
        f"primary_role={account['primary_role']}",
        f"role_scopes={','.join(account['role_scopes'])}",
        f"preferred_source={account['preferred_source']}",
        f"legacy_rows={len(account['legacy_rows'])}",
    ]
    for note in [*account["notes"], *sync_notes]:
        lines.append(f"note={note}")
    return "\n".join(lines)


class Command(BaseCommand):
    help = "Merge legacy customer_db + staff_db accounts into user_service auth_user."

    def add_arguments(self, parser):
        parser.add_argument("--customer-db", default="customer_db")
        parser.add_argument("--staff-db", default="staff_db")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        legacy_rows = _fetch_legacy_users(options["customer_db"], LegacyUserMapping.SOURCE_CUSTOMER)
        legacy_rows.extend(_fetch_legacy_users(options["staff_db"], LegacyUserMapping.SOURCE_STAFF))

        merged_accounts = merge_legacy_accounts(legacy_rows)
        self.stdout.write(f"legacy_rows={len(legacy_rows)} merged_accounts={len(merged_accounts)}")

        if options["dry_run"]:
            for account in merged_accounts[:10]:
                self.stdout.write(
                    f"[dry-run] {format_account_report(account)}"
                )
            return

        created = 0
        updated = 0
        mapping_count = 0
        matched_by_email = 0
        matched_by_username = 0
        conflict_count = 0
        for account in merged_accounts:
            lookup, existing_match = _find_existing_user(account)

            if lookup is None:
                merged_is_superuser = bool(account["is_superuser"])
                merged_is_staff = bool(account["is_staff"] or merged_is_superuser)
                lookup = User.objects.create(
                    username=account["username"],
                    email=account["email"],
                    password=account["password"],
                    first_name=account["first_name"],
                    last_name=account["last_name"],
                    is_staff=merged_is_staff,
                    is_superuser=merged_is_superuser,
                )
                created += 1
                action = "created"
                sync_notes = []
            else:
                updated += 1
                if existing_match == "email":
                    matched_by_email += 1
                elif existing_match == "username":
                    matched_by_username += 1
                action = "updated"
                sync_notes = _sync_account_to_user(lookup, account)

            if account["notes"] or sync_notes:
                conflict_count += 1

            report_line = (
                f"[merge] action={action} "
                f"existing_match={existing_match or 'created'} "
                f"user_id={lookup.pk} "
                f"{format_account_report(account)}"
            )
            if sync_notes:
                report_line += f" sync_notes={len(sync_notes)}"
            self.stdout.write(report_line)
            for note in [*account["notes"], *sync_notes]:
                self.stdout.write(f"[merge-note] user_id={lookup.pk} {note}")

            for legacy_row in account["legacy_rows"]:
                _, mapping_created = LegacyUserMapping.objects.update_or_create(
                    legacy_source=legacy_row["source"],
                    legacy_user_id=legacy_row["id"],
                    defaults={
                        "user": lookup,
                        "legacy_username": legacy_row.get("username") or "",
                        "legacy_email": legacy_row.get("email") or "",
                        "note": _build_mapping_note(
                            account,
                            action=action,
                            existing_match=existing_match,
                            sync_notes=sync_notes,
                        ),
                    },
                )
                if mapping_created:
                    mapping_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Legacy user migration complete. "
                f"created={created} updated={updated} matched_email={matched_by_email} "
                f"matched_username={matched_by_username} conflicts={conflict_count} mappings={mapping_count}"
            )
        )
