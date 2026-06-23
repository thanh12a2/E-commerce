from django.urls import path

from . import views

urlpatterns = [
    path("gateway/", views.gateway_dashboard_view, name="customer_gateway_dashboard"),
    path("gateway/apis/", views.gateway_apis_view, name="customer_gateway_apis"),
    path("", views.home_view, name="customer_home"),
    path("customer/login/", views.customer_login_view, name="customer_login"),
    path("customer/register/", views.customer_register_view, name="customer_register"),
    path("customer/logout/", views.customer_logout_view, name="customer_logout"),
    path("customer/dashboard/", views.customer_dashboard_view, name="customer_dashboard"),
    path("customer/saved/", views.saved_view, name="customer_saved"),
    path("customer/saved/toggle/", views.toggle_save_view, name="customer_toggle_save"),
    path("customer/compare/", views.compare_view, name="customer_compare"),
    path("customer/compare/toggle/", views.toggle_compare_view, name="customer_toggle_compare"),
    path("customer/compare/remove/<int:item_id>/", views.remove_compare_item_view, name="customer_remove_compare_item"),
    path("customer/blog/<slug:slug>/", views.blog_detail_view, name="customer_blog_detail"),
    path(
        "customer/products/<slug:category_slug>/<int:product_id>/",
        views.product_detail_view,
        name="customer_product_detail",
    ),
    path("customer/cart/", views.cart_view, name="customer_cart"),
    path("customer/cart/add/", views.add_to_cart_view, name="customer_add_to_cart"),
    path("customer/cart/remove/<int:item_id>/", views.remove_from_cart_view, name="customer_remove_from_cart"),
    path("customer/chatbot/reply/", views.chatbot_reply_view, name="customer_chatbot_reply"),
    path("customer/staff/analytics/", views.staff_order_analytics_view, name="customer_staff_analytics"),
    path("customer/checkout/", views.checkout_view, name="customer_checkout"),
    path("customer/orders/", views.orders_view, name="customer_orders"),
    path("customer/orders/<int:order_id>/pay/", views.pay_order_view, name="customer_pay_order"),
]
