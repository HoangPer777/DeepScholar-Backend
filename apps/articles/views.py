from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.articles.models import Article
from apps.articles.serializers import ArticleSerializer


class ArticleListCreateView(generics.ListCreateAPIView):
    """TODO: List and create articles"""
    serializer_class = ArticleSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        # TODO: Implement filtered queryset
        pass


class ArticleDetailView(generics.RetrieveUpdateDestroyAPIView):
    """TODO: Get/Update/Delete article"""
    serializer_class = ArticleSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    lookup_field = "slug"

    def get_queryset(self):
        # TODO: Implement filtered queryset
        pass

    def retrieve(self, request, *args, **kwargs):
        # TODO: Increment view count
        pass

    def perform_destroy(self, instance):
        # TODO: Implement soft delete
        pass


class UploadUrlView(APIView):
    """TODO: Generate presigned upload URL for S3/MinIO"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        # TODO: Generate presigned URL for PDF upload
        pass