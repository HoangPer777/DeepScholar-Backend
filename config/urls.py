from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('apps.users.urls')),
    path('api/v1/', include('apps.articles.urls')),
    path('api/v1/', include('apps.interactions.urls')),
    path('api/v1/', include('apps.ranking.urls')),
]
