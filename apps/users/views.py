from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.db.models import F
from django.shortcuts import get_object_or_404
from django.contrib.auth.tokens import default_token_generator
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str

from apps.users.models import User, Author, Notification
from apps.interactions.models import AuthorFollow
from apps.users.serializers import (
    RegisterSerializer,
    CustomTokenObtainPairSerializer,
    UserSerializer,
    AuthorSerializer,
    NotificationSerializer,
    SocialAuthSerializer
)
import requests
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

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
    def post(self, request):
        token = request.data.get('id_token')
        role = request.data.get('role', 'user')
        if not token:
            return Response({"detail": "id_token is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Note: For production, you must set audience to your Client ID
            idinfo = id_token.verify_oauth2_token(token, google_requests.Request(), clock_skew_in_seconds=10)
            serializer = SocialAuthSerializer(data={
                'email': idinfo.get('email'),
                'full_name': idinfo.get('name', ''),
                'provider_id': idinfo.get('sub'),
                'avatar_url': idinfo.get('picture', ''),
                'role': role
            })
            if serializer.is_valid():
                user = serializer.save(provider='google')
                refresh = RefreshToken.for_user(user)
                return Response({
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                    'user': UserSerializer(user).data
                }, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as e:
            return Response({"detail": f"Invalid Google token: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)


class FacebookAuthView(BaseSocialAuthView):
    """Handle Facebook OAuth login"""
    def post(self, request):
        access_token = request.data.get('access_token')
        role = request.data.get('role', 'user')
        if not access_token:
            return Response({"detail": "access_token is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            graph_url = f"https://graph.facebook.com/me?fields=id,name,email,picture&access_token={access_token}"
            fb_res = requests.get(graph_url)
            fb_data = fb_res.json()
            
            if 'error' in fb_data:
                return Response({"detail": "Invalid Facebook token"}, status=status.HTTP_400_BAD_REQUEST)
                
            serializer = SocialAuthSerializer(data={
                'email': fb_data.get('email', f"{fb_data.get('id')}@facebook.com"),
                'full_name': fb_data.get('name', ''),
                'provider_id': fb_data.get('id'),
                'avatar_url': fb_data.get('picture', {}).get('data', {}).get('url', ''),
                'role': role
            })
            if serializer.is_valid():
                user = serializer.save(provider='facebook')
                refresh = RefreshToken.for_user(user)
                return Response({
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                    'user': UserSerializer(user).data
                }, status=status.HTTP_200_OK)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"detail": str(e)}, status=status.HTTP_400_BAD_REQUEST)

class PasswordResetRequestView(APIView):
    """Request password reset link"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({"detail": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        user = User.objects.filter(email=email).first()
        if user:
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            # In a real app, send email here. For now, print to console.
            reset_link = f"http://localhost:3000/reset-password?uid={uid}&token={token}"
            print(f"PASSWORD RESET LINK: {reset_link}")
            
        return Response({"detail": "If an account with this email exists, a reset link has been sent."}, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    """Confirm password reset"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        uidb64 = request.data.get('uid')
        token = request.data.get('token')
        new_password = request.data.get('new_password')
        
        if not all([uidb64, token, new_password]):
            return Response({"detail": "Missing parameters"}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = User.objects.get(pk=uid)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            user = None
            
        if user is not None and default_token_generator.check_token(user, token):
            user.set_password(new_password)
            user.save()
            return Response({"detail": "Password has been reset with the new password."}, status=status.HTTP_200_OK)
        else:
            return Response({"detail": "Invalid token or user ID."}, status=status.HTTP_400_BAD_REQUEST)

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


from rest_framework.filters import SearchFilter

class AuthorRankingView(generics.ListAPIView):
    """Get authors ordered by score"""
    queryset = Author.objects.all().order_by('-total_score')
    serializer_class = AuthorSerializer
    permission_classes = [permissions.AllowAny]
    filter_backends = [SearchFilter]
    search_fields = ['author_code', 'user__full_name', 'affiliation']


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