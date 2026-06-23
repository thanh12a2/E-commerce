from rest_framework import serializers

from .models import Shipment


class ShipmentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Shipment
        fields = [
            "id",
            "order_id",
            "user_id",
            "recipient_name",
            "phone",
            "address_line",
            "city_or_region",
            "postal_code",
            "country",
            "note",
            "status",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def validate_order_id(self, value):
        if value <= 0:
            raise serializers.ValidationError("order_id must be greater than zero.")
        return value

    def validate_user_id(self, value):
        if value <= 0:
            raise serializers.ValidationError("user_id must be greater than zero.")
        return value

    def validate_status(self, value):
        if self.instance is None and value != Shipment.STATUS_PENDING:
            raise serializers.ValidationError("Shipments must be created with pending status.")
        return value

    def validate(self, attrs):
        text_fields = ["recipient_name", "phone", "address_line", "city_or_region", "postal_code", "country", "note"]
        for field in text_fields:
            if field in attrs:
                attrs[field] = str(attrs[field]).strip()
        for field in text_fields[:-1]:
            if field in attrs and not attrs[field]:
                raise serializers.ValidationError({field: "This field may not be blank."})
        return attrs
