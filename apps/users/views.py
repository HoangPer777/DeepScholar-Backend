import logging
import time

from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.shortcuts import get_object_or_404
from django.conf import settings
from django.core.mail import send_mail
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
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
    SocialAuthSerializer,
    BecomeAuthorSerializer,
)
import requests
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests


logger = logging.getLogger(__name__)


class _FacebookConfigurationError(Exception):
    """Raised when Facebook OAuth cannot be safely verified."""


class _FacebookProviderError(Exception):
    """Raised when the Facebook Graph API cannot be trusted for this request."""


class _InvalidFacebookTokenError(Exception):
    """Raised when Facebook rejects or does not prove the supplied token."""


def _facebook_graph_url(path):
    version = getattr(settings, "FACEBOOK_GRAPH_API_VERSION", "")
    base_url = "https://graph.facebook.com"
    if version:
        base_url = f"{base_url}/{version.strip('/')}"
    return f"{base_url}/{path.lstrip('/')}"


def _facebook_graph_get(path, params):
    """Call Facebook without exposing token-bearing request details in logs."""
    try:
        response = requests.get(
            _facebook_graph_url(path),
            params=params,
            timeout=settings.FACEBOOK_GRAPH_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        logger.warning(
            "Facebook OAuth provider request failed: %s",
            exc.__class__.__name__,
        )
        raise _FacebookProviderError from exc

    if response.status_code == 429 or response.status_code >= 500:
        logger.warning(
            "Facebook OAuth provider returned status=%s",
            response.status_code,
        )
        raise _FacebookProviderError
    if not response.ok:
        raise _InvalidFacebookTokenError

    try:
        payload = response.json()
    except (TypeError, ValueError) as exc:
        logger.warning("Facebook OAuth provider returned malformed JSON")
        raise _FacebookProviderError from exc

    if not isinstance(payload, dict):
        logger.warning("Facebook OAuth provider returned an unexpected payload")
        raise _FacebookProviderError
    return payload


def _facebook_timestamp_is_expired(value, now):
    if value in (None, "", 0, "0"):
        return False
    try:
        timestamp = int(value)
    except (TypeError, ValueError):
        return True
    return timestamp <= now


def _validate_facebook_access_token(access_token):
    app_id = getattr(settings, "FACEBOOK_APP_ID", "").strip()
    app_secret = getattr(settings, "FACEBOOK_APP_SECRET", "").strip()
    if not app_id or not app_secret:
        raise _FacebookConfigurationError

    debug_payload = _facebook_graph_get(
        "/debug_token",
        {
            "input_token": access_token,
            "access_token": f"{app_id}|{app_secret}",
        },
    )
    debug_data = debug_payload.get("data")
    if not isinstance(debug_data, dict):
        raise _InvalidFacebookTokenError

    if debug_data.get("is_valid") is not True:
        raise _InvalidFacebookTokenError
    if str(debug_data.get("app_id", "")) != app_id:
        raise _InvalidFacebookTokenError

    user_id = debug_data.get("user_id")
    if not user_id:
        raise _InvalidFacebookTokenError

    token_type = debug_data.get("type")
    if token_type and str(token_type).upper() != "USER":
        raise _InvalidFacebookTokenError

    now = int(time.time())
    for expiry_field in (
        "expires_at",
        "data_access_expiration_time",
        "data_access_expires_at",
    ):
        if _facebook_timestamp_is_expired(debug_data.get(expiry_field), now):
            raise _InvalidFacebookTokenError

    return str(user_id)


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


class BecomeAuthorView(APIView):
    """Promote the authenticated user and create an author profile."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = BecomeAuthorSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user, _, created = serializer.save()

        refresh = CustomTokenObtainPairSerializer.get_token(user)
        return Response({
            'detail': 'Author profile created successfully.' if created else 'Author profile is already active.',
            'created': created,
            'refresh': str(refresh),
            'access': str(refresh.access_token),
            'user': UserSerializer(user).data,
        }, status=status.HTTP_200_OK)


class BaseSocialAuthView(APIView):
    """Base class for OAuth social login"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        return Response({"detail": "OAuth login not implemented yet. Placeholder."}, status=status.HTTP_501_NOT_IMPLEMENTED)


class GoogleAuthView(BaseSocialAuthView):
    """Handle Google OAuth login"""
    def post(self, request):
        token = request.data.get('id_token')
        if not token:
            return Response({"detail": "id_token is required"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Verify the ID token using Google's verification library
            # BUG-006: Ensure audience is validated against our Client ID
            idinfo = id_token.verify_oauth2_token(
                token, 
                google_requests.Request(), 
                audience=settings.GOOGLE_CLIENT_ID or None,
                clock_skew_in_seconds=10
            )
            serializer = SocialAuthSerializer(data={
                'email': idinfo.get('email'),
                'full_name': idinfo.get('name', ''),
                'provider_id': idinfo.get('sub'),
                'avatar_url': idinfo.get('picture', ''),
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
        if not isinstance(access_token, str) or not access_token.strip():
            return Response({"detail": "access_token is required"}, status=status.HTTP_400_BAD_REQUEST)

        access_token = access_token.strip()
        try:
            verified_user_id = _validate_facebook_access_token(access_token)
            fb_data = _facebook_graph_get(
                "/me",
                {
                    "fields": "id,name,picture",
                    "access_token": access_token,
                },
            )

            if "error" in fb_data:
                raise _InvalidFacebookTokenError

            facebook_user_id = fb_data.get("id")
            if not facebook_user_id or str(facebook_user_id) != verified_user_id:
                raise _InvalidFacebookTokenError

            picture = fb_data.get("picture")
            picture_data = picture.get("data") if isinstance(picture, dict) else {}
            avatar_url = picture_data.get("url", "") if isinstance(picture_data, dict) else ""
            facebook_user_id = str(facebook_user_id)
            serializer = SocialAuthSerializer(data={
                'email': fb_data.get('email') or f"{facebook_user_id}@facebook.com",
                'full_name': fb_data.get('name', ''),
                'provider_id': facebook_user_id,
                'avatar_url': avatar_url,
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
        except _FacebookConfigurationError:
            return Response(
                {"detail": "Facebook login is not configured."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )
        except _InvalidFacebookTokenError:
            return Response(
                {"detail": "Invalid Facebook token"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except _FacebookProviderError:
            return Response(
                {"detail": "Facebook login is temporarily unavailable."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

class PasswordResetRequestView(APIView):
    """Request password reset link"""
    permission_classes = [permissions.AllowAny]

    def post(self, request):
        email = request.data.get('email')
        if not email:
            return Response({"detail": "Email is required"}, status=status.HTTP_400_BAD_REQUEST)
            
        user = User.objects.filter(email=email).first()
        if user:
            frontend_url = (settings.FRONTEND_URL or "").rstrip("/")
            if not frontend_url:
                return Response({"detail": "If an account with this email exists, a reset link has been sent."}, status=status.HTTP_200_OK)
            token = default_token_generator.make_token(user)
            uid = urlsafe_base64_encode(force_bytes(user.pk))
            reset_link = f"{frontend_url}/reset-password?uid={uid}&token={token}"
            send_mail(
                subject="DeepScholar Password Reset",
                message=f"Reset your password using this link: {reset_link}",
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
            
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


class ChangePasswordView(APIView):
    """Change password for authenticated user"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')

        if not all([current_password, new_password, confirm_password]):
            return Response({"detail": "Missing required fields."}, status=status.HTTP_400_BAD_REQUEST)

        if new_password != confirm_password:
            return Response({"detail": "New password and confirmation do not match."}, status=status.HTTP_400_BAD_REQUEST)

        user = request.user

        if not user.check_password(current_password):
            return Response({"detail": "Current password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)

        if current_password == new_password:
            return Response({"detail": "New password must be different from current password."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(new_password, user=user)
        except ValidationError as e:
            message = e.messages[0] if e.messages else "Password is invalid."
            return Response({"detail": message}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save(update_fields=['password'])
        return Response({"detail": "Password updated successfully."}, status=status.HTTP_200_OK)

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


class AuthorDetailView(generics.RetrieveUpdateAPIView):
    """Get author public profile or update own author profile"""
    queryset = Author.objects.all()
    serializer_class = AuthorSerializer

    def get_permissions(self):
        if self.request.method in permissions.SAFE_METHODS:
            return [permissions.AllowAny()]
        return [permissions.IsAuthenticated()]

    def update(self, request, *args, **kwargs):
        instance = self.get_object()
        if instance.user_id != request.user.id:
            return Response({"detail": "You do not have permission to edit this author profile."}, status=status.HTTP_403_FORBIDDEN)
        return super().update(request, *args, **kwargs)


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
            # AuthorFollow signals are the single owner of follower_count.
            return Response({"detail": "Successfully followed the author."}, status=status.HTTP_200_OK)
        else:
            # Unfollow
            follow_record.delete()
            return Response({"detail": "Successfully unfollowed the author."}, status=status.HTTP_200_OK)


class NotificationListView(generics.ListAPIView):
    """List user notifications"""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user).order_by('-created_at')


class NotificationReadView(APIView):
    """Mark notification as read"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response({"detail": "Notification marked as read."}, status=status.HTTP_200_OK)
