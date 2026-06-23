from datetime import date

from django.core.management.base import BaseCommand

from customer.models import BlogPost, Testimonial


BLOG_POSTS = [
    {
        "title": "How to Build a Productive Hybrid Workspace in 2026",
        "slug": "hybrid-workspace-2026",
        "category": "Workspace",
        "author": "Editorial Team",
        "excerpt": "A practical blueprint for choosing devices, accessories, and layout habits that improve focus in hybrid teams.",
        "body": "A productive workspace is less about expensive gear and more about consistency. Start with one reliable compute device, one audio setup, and one charging routine. Then reduce friction by keeping cables organized and your desk lighting stable throughout the day. For hybrid teams, camera quality and microphone clarity are often more important than raw benchmark numbers. Invest in accessories that improve daily communication first, then optimize the rest.",
        "hero_image_url": "https://images.unsplash.com/photo-1497366216548-37526070297c?auto=format&fit=crop&w=1400&q=80",
        "published_at": date(2026, 3, 21),
    },
    {
        "title": "Laptop Buying Guide: What Actually Matters for Developers",
        "slug": "laptop-buying-guide-developers",
        "category": "Buying Guide",
        "author": "Ethan Brooks",
        "excerpt": "Processor names can be confusing. This guide simplifies memory, thermal, battery, and display priorities for coding workloads.",
        "body": "For developer workloads, stability under sustained load matters more than short burst scores. Prioritize 16GB+ memory, reliable thermals, and keyboard quality. If your workflow includes containers and local databases, look for balanced CPU and fast storage over high-end GPU. Battery life should support at least one full work block. A brighter matte display can reduce eye strain in mixed lighting conditions.",
        "hero_image_url": "https://images.unsplash.com/photo-1517694712202-14dd9538aa97?auto=format&fit=crop&w=1400&q=80",
        "published_at": date(2026, 3, 14),
    },
    {
        "title": "Mobile Camera Workflow for Creators on the Go",
        "slug": "mobile-camera-workflow-creators",
        "category": "Mobile",
        "author": "Leila Carter",
        "excerpt": "Capture cleaner footage with predictable color and less editing time using a repeatable mobile workflow.",
        "body": "A repeatable mobile camera workflow starts with consistency. Lock frame rate and exposure where possible, use a compact tripod for stability, and carry one reliable wireless audio option. Shoot in similar color profiles to speed up editing. If you publish short-form content frequently, establish a simple transfer routine using a portable SSD and cloud backup so nothing is lost between sessions.",
        "hero_image_url": "https://images.unsplash.com/photo-1511707171634-5f897ff02aa9?auto=format&fit=crop&w=1400&q=80",
        "published_at": date(2026, 3, 8),
    },
    {
        "title": "Why Product Detail Pages Win or Lose Customer Trust",
        "slug": "product-detail-page-trust",
        "category": "E-commerce",
        "author": "Ava Mitchell",
        "excerpt": "Great product pages reduce uncertainty. Here are the sections that improve confidence and conversion.",
        "body": "A strong product detail page answers four questions fast: what it is, why it fits, how much it costs, and what happens next. Clear pricing, visible stock, practical specs, and authentic reviews reduce hesitation. Related products should feel useful, not random. Customers trust pages that are easy to scan and transparent about trade-offs.",
        "hero_image_url": "https://images.unsplash.com/photo-1523275335684-37898b6baf30?auto=format&fit=crop&w=1400&q=80",
        "published_at": date(2026, 2, 26),
    },
]


TESTIMONIALS = [
    {
        "name": "Ava Mitchell",
        "role": "Creative Director",
        "rating": 5,
        "quote": "The product pages are clear and the checkout process is fast. It feels polished and trustworthy end-to-end.",
        "avatar_url": "https://images.unsplash.com/photo-1494790108377-be9c29b29330?auto=format&fit=crop&w=300&q=80",
        "is_featured": True,
    },
    {
        "name": "Noah Bennett",
        "role": "Music Producer",
        "rating": 5,
        "quote": "Accessories are practical and shipping updates are accurate. The experience has been consistently reliable.",
        "avatar_url": "https://images.unsplash.com/photo-1500648767791-00dcc994a43e?auto=format&fit=crop&w=300&q=80",
        "is_featured": True,
    },
    {
        "name": "Liam Reed",
        "role": "Audio Engineer",
        "rating": 5,
        "quote": "I found what I needed quickly with the new filters. Product details are much easier to compare now.",
        "avatar_url": "https://images.unsplash.com/photo-1507003211169-0a1dd7228f2d?auto=format&fit=crop&w=300&q=80",
        "is_featured": True,
    },
    {
        "name": "Ethan Walker",
        "role": "Brand Designer",
        "rating": 4,
        "quote": "Design language is modern and readable. The order flow from cart to payment is straightforward.",
        "avatar_url": "https://images.unsplash.com/photo-1472099645785-5658abf4ff4e?auto=format&fit=crop&w=300&q=80",
        "is_featured": True,
    },
    {
        "name": "Leila Carter",
        "role": "Content Strategist",
        "rating": 5,
        "quote": "I like how related products are shown on detail pages. It helps decision-making without feeling pushy.",
        "avatar_url": "https://images.unsplash.com/photo-1438761681033-6461ffad8d80?auto=format&fit=crop&w=300&q=80",
        "is_featured": True,
    },
]


class Command(BaseCommand):
    help = "Seed blog posts and testimonials for the customer storefront"

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Delete existing blog posts and testimonials before seeding")

    def handle(self, *args, **options):
        if options["reset"]:
            deleted_blog, _ = BlogPost.objects.all().delete()
            deleted_testimonial, _ = Testimonial.objects.all().delete()
            self.stdout.write(self.style.WARNING(f"Deleted {deleted_blog} blog rows and {deleted_testimonial} testimonial rows."))

        created_blog = 0
        updated_blog = 0
        for item in BLOG_POSTS:
            _, created = BlogPost.objects.update_or_create(
                slug=item["slug"],
                defaults=item,
            )
            if created:
                created_blog += 1
            else:
                updated_blog += 1

        created_testimonial = 0
        updated_testimonial = 0
        for item in TESTIMONIALS:
            _, created = Testimonial.objects.update_or_create(
                name=item["name"],
                role=item["role"],
                defaults=item,
            )
            if created:
                created_testimonial += 1
            else:
                updated_testimonial += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Editorial seed complete. "
                f"Blog created: {created_blog}, blog updated: {updated_blog}, "
                f"Testimonials created: {created_testimonial}, testimonials updated: {updated_testimonial}."
            )
        )
