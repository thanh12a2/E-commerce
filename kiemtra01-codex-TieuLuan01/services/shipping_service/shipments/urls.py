from django.urls import path

from . import views

urlpatterns = [
    path("shipments/", views.ShipmentCollectionView.as_view(), name="shipment_collection"),
    path("shipments/<int:shipment_id>/", views.ShipmentDetailView.as_view(), name="shipment_detail"),
    path("shipments/by-order/<int:order_id>/", views.ShipmentByOrderView.as_view(), name="shipment_by_order"),
    path("shipments/<int:shipment_id>/status/", views.ShipmentStatusView.as_view(), name="shipment_status"),
]
