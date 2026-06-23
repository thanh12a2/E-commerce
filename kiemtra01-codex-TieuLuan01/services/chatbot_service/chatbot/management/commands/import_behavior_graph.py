import os

from django.core.management.base import BaseCommand, CommandError

from chatbot.behavior_graph import build_behavior_graph_payload, sync_behavior_graph, write_behavior_graph_demo_svg


def _load_graph_database():
    try:
        from neo4j import GraphDatabase
    except ImportError as exc:
        raise CommandError("neo4j driver is not installed. Add it to chatbot_service requirements first.") from exc
    return GraphDatabase


class Command(BaseCommand):
    help = "Import the synthetic behavior dataset into Neo4j as a knowledge graph."

    def add_arguments(self, parser):
        parser.add_argument("--dataset-path", type=str, default="")
        parser.add_argument("--uri", type=str, default="")
        parser.add_argument("--username", type=str, default="")
        parser.add_argument("--password", type=str, default="")
        parser.add_argument("--database", type=str, default="")
        parser.add_argument("--batch-size", type=int, default=250)
        parser.add_argument("--max-preferences", type=int, default=3)
        parser.add_argument("--preference-share-threshold", type=float, default=0.18)
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing User/Behavior/Category/Product nodes before importing the dataset again.",
        )

    def handle(self, *args, **options):
        uri = (options.get("uri") or os.getenv("NEO4J_URI") or "bolt://neo4j:7687").strip()
        username = (options.get("username") or os.getenv("NEO4J_USERNAME") or "neo4j").strip()
        password = (options.get("password") or os.getenv("NEO4J_PASSWORD") or "graph_password").strip()
        database = (options.get("database") or os.getenv("NEO4J_DATABASE") or "neo4j").strip()
        dataset_path = (options.get("dataset_path") or "").strip() or None
        batch_size = max(1, int(options.get("batch_size") or 250))
        max_preferences = max(1, int(options.get("max_preferences") or 3))
        preference_share_threshold = float(options.get("preference_share_threshold") or 0.18)

        try:
            payload = build_behavior_graph_payload(
                dataset_path=dataset_path,
                preference_share_threshold=preference_share_threshold,
                max_preferences_per_user=max_preferences,
            )
        except FileNotFoundError as exc:
            raise CommandError(f"Dataset file not found: {dataset_path or 'data_user500.csv'}") from exc
        graph_image_path = write_behavior_graph_demo_svg(payload)
        GraphDatabase = _load_graph_database()

        try:
            driver = GraphDatabase.driver(uri, auth=(username, password))
        except Exception as exc:
            raise CommandError(f"Unable to create Neo4j driver for {uri}: {exc}") from exc

        try:
            verify_connectivity = getattr(driver, "verify_connectivity", None)
            if callable(verify_connectivity):
                verify_connectivity()
            with driver.session(database=database) as session:
                stats = sync_behavior_graph(
                    session,
                    payload,
                    clear_existing=bool(options.get("reset")),
                    batch_size=batch_size,
                )
        except Exception as exc:
            raise CommandError(f"Neo4j import failed: {exc}") from exc
        finally:
            close = getattr(driver, "close", None)
            if callable(close):
                close()

        self.stdout.write(self.style.SUCCESS("behavior graph imported."))
        self.stdout.write(f"dataset_path={payload['dataset_path']}")
        self.stdout.write(f"user_count={stats['user_count']}")
        self.stdout.write(f"behavior_count={stats['behavior_count']}")
        self.stdout.write(f"category_count={stats['category_count']}")
        self.stdout.write(f"product_count={stats['product_count']}")
        self.stdout.write(f"preference_count={stats['preference_count']}")
        self.stdout.write(f"catalog_source={stats['catalog_source']}")
        self.stdout.write(f"missing_product_count={stats['missing_product_count']}")
        if graph_image_path:
            self.stdout.write(f"demo_graph_path={graph_image_path}")
