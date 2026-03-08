from django.urls import path

from apps.users.views import (
    AuthorDetailView,
    AuthorFollowToggleView,
    AuthorRankingView,
    CustomTokenObtainPairView,
    FacebookAuthView,
    GoogleAuthView,
    MeView,
    NotificationListView,
    NotificationReadView,
    RegisterView,
    UserDetailView,
)

urlpatterns = [
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", CustomTokenObtainPairView.as_view(), name="auth-login"),
    path("auth/google/", GoogleAuthView.as_view(), name="auth-google"),
    path("auth/facebook/", FacebookAuthView.as_view(), name="auth-facebook"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
    path("users/<int:pk>/", UserDetailView.as_view(), name="user-detail"),
    path("authors/ranking/", AuthorRankingView.as_view(), name="author-ranking"),
    path("authors/<int:pk>/", AuthorDetailView.as_view(), name="author-detail"),
    path("authors/<int:pk>/follow/", AuthorFollowToggleView.as_view(), name="author-follow-toggle"),
    path("notifications/", NotificationListView.as_view(), name="notification-list"),
    path("notifications/<int:pk>/read/", NotificationReadView.as_view(), name="notification-read"),
]