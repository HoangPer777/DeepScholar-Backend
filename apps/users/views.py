from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView


class RegisterView(APIView):
    """TODO: Implement user registration with email/password"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # TODO: Validate input, create user, return JWT tokens
        pass


class CustomTokenObtainPairView(APIView):
    """TODO: Implement JWT login endpoint"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # TODO: Validate credentials, return access/refresh tokens
        pass


class MeView(APIView):
    """TODO: Return authenticated user profile"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        # TODO: Return current user data
        pass


class BaseSocialAuthView(APIView):
    """TODO: Base class for OAuth social login"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        # TODO: Implement OAuth token verification (Google/Facebook)
        pass


class GoogleAuthView(BaseSocialAuthView):
    """TODO: Handle Google OAuth login"""
    pass


class FacebookAuthView(BaseSocialAuthView):
    """TODO: Handle Facebook OAuth login"""
    pass


class UserDetailView(generics.RetrieveUpdateAPIView):
    """TODO: Get/Update user profile"""
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # TODO: Implement queryset
        pass


class AuthorDetailView(generics.RetrieveAPIView):
    """TODO: Get author public profile"""
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        # TODO: Implement queryset
        pass


class AuthorFollowToggleView(APIView):
    """TODO: Toggle follow author"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        # TODO: Implement follow/unfollow logic
        pass


class NotificationListView(generics.ListAPIView):
    """TODO: List user notifications"""
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # TODO: Implement queryset filtered by user
        pass


class NotificationReadView(APIView):
    """TODO: Mark notification as read"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        # TODO: Mark notification read status
        pass