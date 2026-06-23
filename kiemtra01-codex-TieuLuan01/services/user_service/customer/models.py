from django.conf import settings
from django.db import models


class BlogPost(models.Model):
    title = models.CharField(max_length=220)
    slug = models.SlugField(unique=True)
    category = models.CharField(max_length=80)
    author = models.CharField(max_length=120)
    excerpt = models.TextField()
    body = models.TextField()
    hero_image_url = models.URLField(blank=True)
    published_at = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-published_at", "-id"]

    def __str__(self):
        return self.title


class Testimonial(models.Model):
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=120)
    rating = models.PositiveSmallIntegerField(default=5)
    quote = models.TextField()
    avatar_url = models.URLField(blank=True)
    is_featured = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.name} ({self.role})"


class LegacyUserMapping(models.Model):
    SOURCE_CUSTOMER = "customer"
    SOURCE_STAFF = "staff"
    SOURCE_CHOICES = [
        (SOURCE_CUSTOMER, "Customer"),
        (SOURCE_STAFF, "Staff"),
    ]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="legacy_mappings")
    legacy_source = models.CharField(max_length=20, choices=SOURCE_CHOICES)
    legacy_user_id = models.PositiveIntegerField()
    legacy_username = models.CharField(max_length=150, blank=True)
    legacy_email = models.EmailField(blank=True)
    note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["legacy_source", "legacy_user_id"]
        unique_together = ("legacy_source", "legacy_user_id")

    def __str__(self):
        return f"{self.legacy_source}:{self.legacy_user_id} -> {self.user_id}"
