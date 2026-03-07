from django.urls import path

from apps.articles.views import ArticleDetailView, ArticleListCreateView, UploadUrlView


urlpatterns = [
    path("articles/", ArticleListCreateView.as_view(), name="article-list-create"),
    path("articles/upload_url/", UploadUrlView.as_view(), name="article-upload-url"),
    path("articles/<slug:slug>/", ArticleDetailView.as_view(), name="article-detail"),
]