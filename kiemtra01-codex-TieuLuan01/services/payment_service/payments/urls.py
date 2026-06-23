from django.urls import path

from . import views

urlpatterns = [
    path("payments/", views.PaymentCollectionView.as_view(), name="payment_collection"),
    path("payments/<int:payment_id>/", views.PaymentDetailView.as_view(), name="payment_detail"),
    path("payments/by-order/<int:order_id>/", views.PaymentByOrderView.as_view(), name="payment_by_order"),
    path("payments/<int:payment_id>/confirm/", views.PaymentConfirmView.as_view(), name="payment_confirm"),
    path("payments/<int:payment_id>/cancel/", views.PaymentCancelView.as_view(), name="payment_cancel"),
]
