from django.urls import path

from . import views

urlpatterns = [
    path("cart/", views.cart_collection_view, name="order_cart_collection"),
    path("cart/<int:item_id>/", views.cart_item_view, name="order_cart_item"),
    path("saved/", views.saved_collection_view, name="order_saved_collection"),
    path("saved/toggle/", views.saved_toggle_view, name="order_saved_toggle"),
    path("compare/", views.compare_collection_view, name="order_compare_collection"),
    path("compare/toggle/", views.compare_toggle_view, name="order_compare_toggle"),
    path("compare/<int:item_id>/", views.compare_item_view, name="order_compare_item"),
    path("checkout/", views.checkout_view, name="order_checkout"),
    path("orders/", views.orders_collection_view, name="order_orders_collection"),
    path("orders/<int:order_id>/pay/", views.pay_order_view, name="order_pay"),
    path("staff/orders/", views.staff_orders_view, name="order_staff_orders"),
    path("staff/orders/<int:order_id>/shipping/", views.staff_shipping_update_view, name="order_staff_shipping"),
    path("analytics/customers/", views.customer_analytics_view, name="order_customer_analytics"),
    path("internal/behavior-source/", views.behavior_source_view, name="order_behavior_source"),
]
