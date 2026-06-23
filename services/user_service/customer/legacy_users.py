from customer.auth_rules import role_scopes_from_sources, resolve_primary_role


def _normalized_email(value):
    return str(value or "").strip().lower()


def _normalized_username(value):
    return str(value or "").strip()


def _base_account(row):
    source = row["source"]
    account = {
        "username": _normalized_username(row.get("username")),
        "email": _normalized_email(row.get("email")),
        "password": row.get("password") or "",
        "first_name": str(row.get("first_name") or "").strip(),
        "last_name": str(row.get("last_name") or "").strip(),
        "is_staff": bool(row.get("is_staff")) or source == "staff",
        "is_superuser": bool(row.get("is_superuser")),
        "legacy_rows": [row],
        "merge_reasons": [],
        "notes": [],
    }
    _refresh_account_metadata(account)
    return account


def _source_priority(source):
    if source == "staff":
        return 1
    return 0


def _refresh_account_metadata(account):
    source_names = [row["source"] for row in account["legacy_rows"]]
    account["preferred_source"] = max(source_names, key=_source_priority)
    account["primary_role"] = resolve_primary_role(
        is_staff=account["is_staff"],
        is_superuser=account["is_superuser"],
    )
    account["role_scopes"] = role_scopes_from_sources(
        source_names=source_names,
        is_staff=account["is_staff"],
        is_superuser=account["is_superuser"],
    )


def format_account_report(account):
    sources = ",".join(sorted({row["source"] for row in account["legacy_rows"]}))
    scopes = ",".join(account["role_scopes"])
    return (
        f"primary_role={account['primary_role']} "
        f"role_scopes={scopes} "
        f"preferred_source={account['preferred_source']} "
        f"legacy_rows={len(account['legacy_rows'])} "
        f"sources={sources} "
        f"username={account['username'] or '-'} "
        f"email={account['email'] or '-'} "
        f"notes={len(account['notes'])}"
    )


def merge_legacy_accounts(rows):
    accounts = []
    email_index = {}
    username_index = {}

    def bind_indices(account):
        if account["email"]:
            email_index[account["email"]] = account
        if account["username"]:
            username_index[account["username"].lower()] = account

    for row in rows:
        email = _normalized_email(row.get("email"))
        username = _normalized_username(row.get("username"))
        account = email_index.get(email) if email else None
        match_reason = None
        username_key = username.lower() if username else ""
        incoming_email_conflict = False
        if account is None and username:
            account = username_index.get(username_key)
            if account is not None:
                current_email = _normalized_email(account.get("email"))
                incoming_email_conflict = bool(current_email and email and current_email != email)
                match_reason = "username"
        elif account is not None:
            match_reason = "email"

        if account is None:
            account = _base_account(row)
            accounts.append(account)
            bind_indices(account)
            continue

        account["legacy_rows"].append(row)
        if match_reason:
            account["merge_reasons"].append(match_reason)
        if incoming_email_conflict:
            account["notes"].append(
                "Username collision across legacy sources: merged by username after email miss "
                f"('{email}' vs '{current_email}')."
            )
        account["is_staff"] = account["is_staff"] or bool(row.get("is_staff")) or row["source"] == "staff"
        account["is_superuser"] = account["is_superuser"] or bool(row.get("is_superuser"))

        preferred_is_new = _source_priority(row["source"]) > _source_priority(account["preferred_source"])
        for field in ["username", "email", "password", "first_name", "last_name"]:
            incoming = _normalized_email(row.get(field)) if field == "email" else str(row.get(field) or "").strip()
            current = account[field]
            if not incoming:
                continue
            if not current:
                account[field] = incoming
                continue
            if current == incoming:
                continue
            if preferred_is_new:
                account["notes"].append(
                    f"Conflict on {field}: preferred staff value '{incoming}' over '{current}'."
                )
                account[field] = incoming
            else:
                account["notes"].append(
                    f"Conflict on {field}: kept existing value '{current}', ignored customer value '{incoming}'."
                )

        _refresh_account_metadata(account)
        bind_indices(account)

    return accounts
