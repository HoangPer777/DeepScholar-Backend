import os
from rest_framework import permissions

class IsInternalService(permissions.BasePermission):
    """
    Allow access if the request contains the correct X-Internal-Service-Key.
    """
    def has_permission(self, request, view):
        internal_key = os.getenv("INTERNAL_SERVICE_KEY")
        if not internal_key:
            return False
        provided_key = request.headers.get("X-Internal-Service-Key")
        return provided_key == internal_key


class IsAuthor(permissions.BasePermission):
    """Allow active authors (and Django administrators) to publish content."""
    message = "You need an active author profile to perform this action."

    def has_permission(self, request, view):
        user = request.user
        if not user or not user.is_authenticated:
            return False
        if user.is_staff or user.is_superuser:
            return True
        author_profile = getattr(user, 'author_profile', None)
        return bool(
            user.role == 'author'
            and author_profile
            and author_profile.is_active
        )
