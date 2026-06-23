import os

from rest_framework.permissions import SAFE_METHODS, BasePermission


class StaffWritePermission(BasePermission):
    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return True

        expected_key = os.getenv("STAFF_API_KEY", "dev-staff-key")
        provided_key = request.headers.get("X-Staff-Key", "")
        return provided_key == expected_key
