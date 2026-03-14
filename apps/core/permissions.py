import os
from rest_framework import permissions

class IsInternalService(permissions.BasePermission):
    """
    Allow access if the request contains the correct X-Internal-Service-Key.
    """
    def has_permission(self, request, view):
        internal_key = os.getenv("INTERNAL_SERVICE_KEY", "deepscholar-secret-key-2026")
        provided_key = request.headers.get("X-Internal-Service-Key")
        return provided_key == internal_key
