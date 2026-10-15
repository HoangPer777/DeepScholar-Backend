from django.contrib import admin
from django.urls import path, include
from apps.articles.ai_proxy import pdf_pipeline_callback, pdf_pipeline_status, trigger_pdf_pipeline

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('apps.users.urls')),
    path('api/v1/', include('apps.articles.urls')),
    path('api/v1/', include('apps.interactions.urls')),
    path('api/v1/', include('apps.ranking.urls')),
    path('api/v1/ai/trigger/', trigger_pdf_pipeline, name='trigger_ai'),
    path('api/v1/ai/status/', pdf_pipeline_status, name='pdf_pipeline_status'),
    path('api/v1/ai/pdf/callback/', pdf_pipeline_callback, name='pdf_pipeline_callback'),
]
