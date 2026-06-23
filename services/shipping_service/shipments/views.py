from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Shipment
from .permissions import InternalKeyPermission
from .serializers import ShipmentSerializer


class InternalAPIView(APIView):
    permission_classes = [InternalKeyPermission]


class ShipmentCollectionView(InternalAPIView):
    def post(self, request):
        serializer = ShipmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        shipment = serializer.save(status=Shipment.STATUS_PENDING)
        return Response(ShipmentSerializer(shipment).data, status=status.HTTP_201_CREATED)


class ShipmentDetailView(InternalAPIView):
    def get(self, request, shipment_id):
        shipment = get_object_or_404(Shipment, id=shipment_id)
        return Response(ShipmentSerializer(shipment).data)


class ShipmentByOrderView(InternalAPIView):
    def get(self, request, order_id):
        shipment = get_object_or_404(Shipment, order_id=order_id)
        return Response(ShipmentSerializer(shipment).data)


class ShipmentStatusView(InternalAPIView):
    def patch(self, request, shipment_id):
        return self._update_status(request, shipment_id)

    def post(self, request, shipment_id):
        return self._update_status(request, shipment_id)

    def _update_status(self, request, shipment_id):
        shipment = get_object_or_404(Shipment, id=shipment_id)
        new_status = str(
            request.data.get("status")
            or request.data.get("shipping_status")
            or ""
        ).strip().lower()
        can_update, message = shipment.can_update_status(new_status)
        if not can_update:
            return Response({"error": message}, status=status.HTTP_400_BAD_REQUEST)

        shipment.status = new_status
        shipment.save(update_fields=["status", "updated_at"])
        return Response(ShipmentSerializer(shipment).data)
