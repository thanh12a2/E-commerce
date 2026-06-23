from decimal import Decimal, InvalidOperation

from django.db.models import Q
from rest_framework import viewsets

from .models import Category, Product
from .permissions import StaffWritePermission
from .serializers import CategorySerializer, ProductSerializer


TRUTHY_VALUES = {"1", "true", "yes", "on"}
FALSY_VALUES = {"0", "false", "no", "off"}


def _parse_decimal(value):
    if value in [None, ""]:
        return None

    try:
        return Decimal(value)
    except (InvalidOperation, TypeError, ValueError):
        return None


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CategorySerializer
    queryset = Category.objects.filter(is_active=True).order_by("sort_order", "name")


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [StaffWritePermission]

    def get_queryset(self):
        queryset = Product.objects.select_related("category").filter(category__is_active=True)
        search = (self.request.query_params.get("search") or "").strip()
        brand = (self.request.query_params.get("brand") or "").strip()
        category = (self.request.query_params.get("category") or "").strip()
        min_price = _parse_decimal(self.request.query_params.get("min_price"))
        max_price = _parse_decimal(self.request.query_params.get("max_price"))
        in_stock = (self.request.query_params.get("in_stock") or "").lower()

        if search:
            queryset = queryset.filter(
                Q(name__icontains=search)
                | Q(description__icontains=search)
                | Q(brand__icontains=search)
                | Q(category__name__icontains=search)
                | Q(category__slug__icontains=search)
            )

        if brand:
            queryset = queryset.filter(brand__icontains=brand)

        if category:
            category_filter = Q(category__slug=category) | Q(category__name__iexact=category)
            if category.isdigit():
                category_filter |= Q(category_id=int(category))
            queryset = queryset.filter(category_filter)

        if min_price is not None:
            queryset = queryset.filter(price__gte=min_price)

        if max_price is not None:
            queryset = queryset.filter(price__lte=max_price)

        if in_stock in TRUTHY_VALUES:
            queryset = queryset.filter(stock__gt=0)
        elif in_stock in FALSY_VALUES:
            queryset = queryset.filter(stock=0)

        return queryset.order_by("category__sort_order", "name", "brand", "id")
