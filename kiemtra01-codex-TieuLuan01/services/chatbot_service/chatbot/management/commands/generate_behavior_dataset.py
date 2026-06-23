from django.core.management.base import BaseCommand

from chatbot.dataset_generation import write_behavior_dataset_bundle


class Command(BaseCommand):
    help = "Generate synthetic ecommerce behavior dataset for 500 users, sequence training, and graph ingestion."

    def add_arguments(self, parser):
        parser.add_argument("--users", type=int, default=500)
        parser.add_argument("--sample-size", type=int, default=20)
        parser.add_argument("--seed", type=int, default=20260420)
        parser.add_argument("--output-dir", type=str, default="")

    def handle(self, *args, **options):
        user_count = max(1, int(options.get("users") or 500))
        sample_size = max(1, int(options.get("sample_size") or 20))
        seed = int(options.get("seed") or 20260420)
        output_dir = (options.get("output_dir") or "").strip() or None

        result = write_behavior_dataset_bundle(
            output_dir=output_dir,
            user_count=user_count,
            sample_size=sample_size,
            seed=seed,
        )
        stats = result["stats"]

        self.stdout.write(self.style.SUCCESS("behavior dataset generated."))
        self.stdout.write(f"user_count={stats['user_count']}")
        self.stdout.write(f"event_count={stats['event_count']}")
        self.stdout.write(f"session_count={stats['session_count']}")
        self.stdout.write(f"catalog_source={stats['catalog_source']}")
        self.stdout.write(f"dataset_file={result['dataset_path']}")
        self.stdout.write(f"sample_file={result['sample_path']}")
        self.stdout.write(f"stats_file={result['stats_path']}")
