from django.urls import path

from apps.users.views import (
    AuthorDetailView,
    CustomTokenObtainPairView,
    FacebookAuthView,
    GoogleAuthView,
    MeView,
    ChangePasswordView,
    RegisterView,
    UserDetailView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
    BecomeAuthorView,
)

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", CustomTokenObtainPairView.as_view(), name="auth-login"),
    path("auth/google/", GoogleAuthView.as_view(), name="auth-google"),
    path("auth/facebook/", FacebookAuthView.as_view(), name="auth-facebook"),
    path("auth/password-reset/", PasswordResetRequestView.as_view(), name="auth-password-reset"),
    path("auth/password-reset-confirm/", PasswordResetConfirmView.as_view(), name="auth-password-reset-confirm"),
    path("auth/change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("auth/become-author/", BecomeAuthorView.as_view(), name="auth-become-author"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="user-detail"),
    path("authors/<int:pk>/", AuthorDetailView.as_view(), name="author-detail"),
    # Note: authors/<pk>/follow/, notifications/, notifications/<pk>/read/
    # are now handled by apps.interactions.urls
]
