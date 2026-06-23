from django.contrib import admin
from django.urls import include, path
from rest_framework_simplejwt.views import TokenRefreshView

from customer.api_auth import AuthTokenView, MeView, RegisterView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/register/', RegisterView.as_view(), name='api_auth_register'),
    path('api/auth/token/', AuthTokenView.as_view(), name='api_auth_token'),
    path('api/auth/token/refresh/', TokenRefreshView.as_view(), name='api_auth_token_refresh'),
    path('api/auth/me/', MeView.as_view(), name='api_auth_me'),
    path('', include('customer.urls')),
    path('staff/', include('staff.urls')),
]
