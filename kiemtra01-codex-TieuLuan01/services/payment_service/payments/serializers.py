from rest_framework import serializers

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = [
            "id",
            "order_id",
            "user_id",
            "amount",
            "status",
            "paid_at",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "paid_at", "created_at", "updated_at"]

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_status(self, value):
        if self.instance is None and value != Payment.STATUS_PENDING:
            raise serializers.ValidationError("Payments must be created with pending status.")
        return value
