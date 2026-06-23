from django.core.management.base import BaseCommand

from chatbot.rag_kb import build_and_save_knowledge_base


class Command(BaseCommand):
    help = "Build unified knowledge base artifacts for chatbot_service"

    def add_arguments(self, parser):
        parser.add_argument("--max-products", type=int, default=120)

    def handle(self, *args, **options):
        max_products = max(10, int(options.get("max_products") or 120))
        payload = build_and_save_knowledge_base(max_products=max_products)
        stats = payload.get("stats") or {}

        self.stdout.write(self.style.SUCCESS("Knowledge base generated."))
        self.stdout.write(f"total_docs={stats.get('total_docs', 0)}")
        self.stdout.write(f"product_docs={stats.get('product_docs', 0)}")
        self.stdout.write(f"faq_docs={stats.get('faq_docs', 0)}")
        self.stdout.write(f"category_count={stats.get('category_count', 0)}")
