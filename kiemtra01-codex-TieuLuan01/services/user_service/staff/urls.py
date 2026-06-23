from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.staff_login_view, name="staff_login"),
    path("register/", views.staff_register_view, name="staff_register"),
    path("logout/", views.staff_logout_view, name="staff_logout"),
    path("dashboard/", views.staff_dashboard_view, name="staff_dashboard"),
    path("items/", views.staff_items_view, name="staff_items"),
    path("customers/", views.staff_customers_view, name="staff_customers"),
    path("customers/<int:user_id>/", views.staff_customer_detail_view, name="staff_customer_detail"),
    path("customers/<int:user_id>/edit/", views.staff_customer_edit_view, name="staff_customer_edit"),
    path("customers/<int:user_id>/toggle-active/", views.staff_customer_toggle_active_view, name="staff_customer_toggle_active"),
    path("customers/<int:user_id>/reset-password/", views.staff_customer_reset_password_view, name="staff_customer_reset_password"),
    path("orders/", views.staff_orders_view, name="staff_orders"),
]
