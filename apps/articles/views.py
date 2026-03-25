import os
import uuid
from django.db.models import F
from rest_framework import viewsets, status, serializers
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAuthenticatedOrReadOnly
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.pagination import PageNumberPagination
from .models import Article
from .serializers import ArticleListSerializer, ArticleDetailSerializer, ArticleCreateUpdateSerializer
from apps.core.permissions import IsInternalService


class ArticlePagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class ArticleViewSet(viewsets.ModelViewSet):
    queryset = Article.objects.filter(is_active=True).prefetch_related('authors')
    lookup_field = 'slug'
    permission_classes = [IsAuthenticatedOrReadOnly | IsInternalService]
    pagination_class = ArticlePagination
    filter_backends = [DjangoFilterBackend, OrderingFilter, SearchFilter]
    filterset_fields = ['authors']
    ordering_fields = ['view_count', 'created_at']
    ordering = ['-created_at']
    search_fields = ['title', 'abstract']

    def get_serializer_class(self):
        if self.action == 'list':
            return ArticleListSerializer
        elif self.action in ['create', 'update', 'partial_update']:
            return ArticleCreateUpdateSerializer
        return ArticleDetailSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        created_after = self.request.query_params.get('created_after')
        created_before = self.request.query_params.get('created_before')
        if created_after:
            qs = qs.filter(created_at__gte=created_after)
        if created_before:
            qs = qs.filter(created_at__lte=created_before)
        return qs

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        # Increment view count atomically
        Article.objects.filter(pk=instance.pk).update(view_count=F('view_count') + 1)
        instance.refresh_from_db()
        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    def _is_internal_service(self, request):
        return IsInternalService().has_permission(request, self)

    def _can_manage_article(self, user, article):
        if not user or not user.is_authenticated:
            return False
        if user.is_staff or user.is_superuser:
            return True
        author_profile = getattr(user, 'author_profile', None)
        if not author_profile:
            return False
        return article.authors.filter(id=author_profile.id).exists()

    def _enforce_article_manage_permission(self, request, article):
        if self._is_internal_service(request):
            return
        if self._can_manage_article(request.user, article):
            return
        raise PermissionDenied("You do not have permission to modify this article.")

    def update(self, request, *args, **kwargs):
        article = self.get_object()
        self._enforce_article_manage_permission(request, article)
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        article = self.get_object()
        self._enforce_article_manage_permission(request, article)
        return super().partial_update(request, *args, **kwargs)

    def perform_create(self, serializer):
        if not hasattr(self.request.user, 'author_profile'):
            raise serializers.ValidationError({"detail": "User is not an author. Only authors can create articles."})
        serializer.save()

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        self._enforce_article_manage_permission(request, instance)
        instance.is_active = False
        instance.save()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def upload_url(self, request):
        """
        Generates a Presigned PUT URL for direct upload to Cloudflare R2.

        Returns:
          - presigned_url: Use this URL to PUT the file directly from the browser
          - file_path:     The object key inside the bucket (e.g. articles/uuid_file.pdf)
          - public_url:    The publicly accessible URL of the file after upload

        The public_url is built from AWS_PUBLIC_URL (your r2.dev or custom domain).
        If not set, falls back to the private storage endpoint (for internal use only).
        """
        endpoint_url = os.getenv('AWS_ENDPOINT_URL')
        aws_access_key_id = os.getenv('AWS_ACCESS_KEY_ID', 'minioadmin')
        aws_secret_access_key = os.getenv('AWS_SECRET_ACCESS_KEY', 'minioadmin')
        bucket_name = os.getenv('AWS_STORAGE_BUCKET_NAME', 'deepscholar-articles')
        region_name = os.getenv('AWS_S3_REGION_NAME', 'apac')
        # Public-facing URL base: set this to your r2.dev URL or custom domain
        # e.g.  https://pub-abc123.r2.dev  OR  https://files.yourdomain.com
        public_base_url = os.getenv('AWS_PUBLIC_URL', '').rstrip('/')

        file_name = request.data.get('file_name')
        if not file_name:
            file_name = f"{uuid.uuid4()}.pdf"

        # Ensure only PDF files are uploaded
        if not file_name.lower().endswith('.pdf'):
            return Response(
                {"error": "Only PDF files are allowed"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Unique object key to avoid collisions
        file_path = f"articles/{uuid.uuid4()}_{file_name}"

        try:
            import boto3
            s3_client = boto3.client(
                's3',
                endpoint_url=endpoint_url,
                aws_access_key_id=aws_access_key_id,
                aws_secret_access_key=aws_secret_access_key,
                region_name=region_name,
                config=boto3.session.Config(signature_version='s3v4')
            )

            presigned_url = s3_client.generate_presigned_url(
                'put_object',
                Params={
                    'Bucket': bucket_name,
                    'Key': file_path,
                    'ContentType': 'application/pdf',
                },
                ExpiresIn=3600  # 1 hour
            )

            # Build the public URL:
            # - If AWS_PUBLIC_URL is configured (recommended), use it → https://pub-xxx.r2.dev/articles/uuid.pdf
            # - Otherwise fall back to the private storage endpoint (only accessible server-side)
            if public_base_url:
                public_url = f"{public_base_url}/{file_path}"
            else:
                # Fallback: private endpoint URL (AI service can still access via boto3)
                public_url = f"{endpoint_url}/{bucket_name}/{file_path}"

            return Response({
                "presigned_url": presigned_url,
                "file_path": file_path,
                "public_url": public_url,
            })
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
