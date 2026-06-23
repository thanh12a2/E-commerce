from rest_framework import serializers

from .models import Category, Product


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "hero_image_url",
            "sort_order",
            "is_active",
        ]


class ProductSerializer(serializers.ModelSerializer):
    category = serializers.PrimaryKeyRelatedField(queryset=Category.objects.filter(is_active=True))
    category_slug = serializers.CharField(source="category.slug", read_only=True)
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Product
        fields = [
            "id",
            "category",
            "category_slug",
            "category_name",
            "name",
            "brand",
            "description",
            "image_url",
            "price",
            "stock",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["category_slug", "category_name", "created_at", "updated_at"]
