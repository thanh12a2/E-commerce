from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Payment
from .permissions import InternalKeyPermission
from .serializers import PaymentSerializer


class InternalAPIView(APIView):
    permission_classes = [InternalKeyPermission]


class PaymentCollectionView(InternalAPIView):
    def post(self, request):
        serializer = PaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = serializer.save(status=Payment.STATUS_PENDING)
        return Response(PaymentSerializer(payment).data, status=status.HTTP_201_CREATED)


class PaymentDetailView(InternalAPIView):
    def get(self, request, payment_id):
        payment = get_object_or_404(Payment, id=payment_id)
        return Response(PaymentSerializer(payment).data)


class PaymentByOrderView(InternalAPIView):
    def get(self, request, order_id):
        payment = get_object_or_404(Payment, order_id=order_id)
        return Response(PaymentSerializer(payment).data)


class PaymentConfirmView(InternalAPIView):
    def post(self, request, payment_id):
        payment = get_object_or_404(Payment, id=payment_id)
        can_confirm, message = payment.can_confirm()
        if not can_confirm:
            return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)

        payment.status = Payment.STATUS_PAID
        payment.paid_at = timezone.now()
        payment.save(update_fields=["status", "paid_at", "updated_at"])
        return Response(PaymentSerializer(payment).data)


class PaymentCancelView(InternalAPIView):
    def post(self, request, payment_id):
        payment = get_object_or_404(Payment, id=payment_id)
        can_cancel, message = payment.can_cancel()
        if not can_cancel:
            return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)

        payment.status = Payment.STATUS_CANCELLED
        payment.paid_at = None
        payment.save(update_fields=["status", "paid_at", "updated_at"])
        return Response(PaymentSerializer(payment).data)
