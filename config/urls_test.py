"""Minimal URL conf for integration tests (no AI proxy, no admin)."""
from django.urls import path, include

urlpatterns = [
    path('api/v1/', include('apps.users.urls')),
    path('api/v1/', include('apps.articles.urls')),
    path('api/v1/', include('apps.interactions.urls')),
    path('api/v1/', include('apps.ranking.urls')),
]
