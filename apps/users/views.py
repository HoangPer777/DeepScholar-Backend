from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.db.models import F
from django.shortcuts import get_object_or_404

from apps.users.models import User, Author, Notification
from apps.interactions.models import AuthorFollow
from apps.users.serializers import (
    RegisterSerializer,
    CustomTokenObtainPairSerializer,
    UserSerializer,
    AuthorSerializer,
    NotificationSerializer
)

class RegisterView(APIView):
    """User registration with email/password"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'user': UserSerializer(user).data
            }, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class CustomTokenObtainPairView(TokenObtainPairView):
    """JWT login endpoint"""
    permission_classes = [permissions.AllowAny]
    serializer_class = CustomTokenObtainPairSerializer


class MeView(APIView):
    """Return authenticated user profile"""
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data)


class BaseSocialAuthView(APIView):
    """Base class for OAuth social login"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        return Response({"detail": "OAuth login not implemented yet. Placeholder."}, status=status.HTTP_501_NOT_IMPLEMENTED)


class GoogleAuthView(BaseSocialAuthView):
    """Handle Google OAuth login"""
    pass


class FacebookAuthView(BaseSocialAuthView):
    """Handle Facebook OAuth login"""
    pass


class UserDetailView(generics.RetrieveUpdateAPIView):
    """Get/Update user profile"""
    queryset = User.objects.all()
    serializer_class = UserSerializer

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance != request.user:
            return Response({"detail": "You do not have permission to edit this user."}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)


class AuthorDetailView(generics.RetrieveAPIView):
    """Get author public profile"""
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer
    permission_classes = [permissions.AllowAny]


class AuthorFollowToggleView(APIView):
    """Toggle follow author"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        followed_author = get_object_or_404(Author, pk=pk)
        
        if not hasattr(request.user, 'author_profile'):
            return Response({"detail": "Only authors can follow other authors in this system."}, status=status.HTTP_400_BAD_REQUEST)
            
        follower_author = request.user.author_profile
        
        # Prevent self-following
        if follower_author == followed_author:
            return Response({"detail": "You cannot follow yourself."}, status=status.HTTP_400_BAD_REQUEST)
            
        follow_record, created = AuthorFollow.objects.get_or_create(
            follower_author=follower_author,
            followed_author=followed_author
        )
        
        if created:
            # New follow
            Author.objects.filter(pk=pk).update(follower_count=F('follower_count') + 1)
            return Response({"detail": "Successfully followed the author."}, status=status.HTTP_200_OK)
        else:
            # Unfollow
            follow_record.delete()
            Author.objects.filter(pk=pk).update(follower_count=F('follower_count') - 1)
            return Response({"detail": "Successfully unfollowed the author."}, status=status.HTTP_200_OK)


class AuthorRankingView(generics.ListAPIView):
    """Get authors ordered by score"""
    queryset = Author.objects.all().order_by('-total_score')
    serializer_class = AuthorSerializer
    permission_classes = [permissions.AllowAny]


class NotificationListView(generics.ListAPIView):
    """List user notifications"""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user).order_by('-created_at')


class NotificationReadView(APIView):
    """Mark notification as read"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, user=request.user)
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response({"detail": "Notification marked as read."}, status=status.HTTP_200_OK)