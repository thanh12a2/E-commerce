from django.contrib import admin

from .models import BlogPost, LegacyUserMapping, Testimonial


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ("title", "category", "author", "published_at")
    search_fields = ("title", "category", "author")
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Testimonial)
class TestimonialAdmin(admin.ModelAdmin):
    list_display = ("name", "role", "rating", "is_featured", "created_at")
    list_filter = ("is_featured", "rating")
    search_fields = ("name", "role")


@admin.register(LegacyUserMapping)
class LegacyUserMappingAdmin(admin.ModelAdmin):
    list_display = ("legacy_source", "legacy_user_id", "legacy_username", "legacy_email", "user")
    list_filter = ("legacy_source",)
    search_fields = ("legacy_username", "legacy_email", "user__username", "user__email")
