from django.contrib import admin
from django.urls import path, include
from apps.articles.ai_proxy import trigger_pdf_pipeline

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('apps.users.urls')),
    path('api/v1/', include('apps.articles.urls')),
    path('api/v1/', include('apps.interactions.urls')),
    path('api/v1/', include('apps.ranking.urls')),
    path('api/v1/ai/trigger/', trigger_pdf_pipeline, name='trigger_ai'),
]
