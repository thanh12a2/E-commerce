import os

import requests
from django.core.management.base import BaseCommand

from customer.services import export_behavior_source


class Command(BaseCommand):
    help = "Backfill chatbot behavior events from order_service order history."

    def add_arguments(self, parser):
        parser.add_argument("--max-events", type=int, default=1200)
        parser.add_argument("--max-users", type=int, default=300)
        parser.add_argument("--source-status", choices=["paid", "all"], default="paid")
        parser.add_argument("--timeout", type=int, default=8)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        records = export_behavior_source(
            max_users=max(1, int(options["max_users"])),
            max_events=max(1, int(options["max_events"])),
            source_status=options["source_status"],
        )
        if not records:
            self.stdout.write(self.style.WARNING("No backfill source records were returned by order_service."))
            return

        base_url = (os.getenv("CHATBOT_SERVICE_URL") or "http://chatbot-service:8000").rstrip("/")
        endpoint = f"{base_url}/api/chat/ingest-behavior/"
        timeout_seconds = max(3, int(options["timeout"]))
        dry_run = bool(options["dry_run"])
        headers = {}
        ingest_key = (os.getenv("CHATBOT_INGEST_KEY") or "").strip()
        if ingest_key:
            headers["X-Ingest-Key"] = ingest_key

        sent = 0
        succeeded = 0
        failed = 0
        sample_errors = []

        for record in records:
            sent += 1
            if dry_run:
                succeeded += 1
                continue

            try:
                response = requests.post(endpoint, json=record, headers=headers, timeout=timeout_seconds)
                if response.ok:
                    succeeded += 1
                else:
                    failed += 1
                    if len(sample_errors) < 5:
                        sample_errors.append(f"http_{response.status_code}: {response.text[:140]}")
            except requests.RequestException as exc:
                failed += 1
                if len(sample_errors) < 5:
                    sample_errors.append(f"request_error: {exc}")

        mode = "DRY-RUN" if dry_run else "LIVE"
        self.stdout.write(
            self.style.SUCCESS(
                f"Backfill ({mode}) finished. source_records={len(records)} sent={sent} success={succeeded} failed={failed} endpoint={endpoint}"
            )
        )
        for error in sample_errors:
            self.stdout.write(self.style.WARNING(f"sample_error: {error}"))
