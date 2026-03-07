from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.articles.models import Article
from apps.interactions.models import Comment
from apps.interactions.serializers import CommentSerializer


class LikeToggleView(APIView):
    """TODO: Toggle like on article"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        # TODO: Implement like/unlike logic
        pass


class BookmarkToggleView(APIView):
    """TODO: Toggle bookmark on article"""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        # TODO: Implement bookmark logic
        pass


class CommentListCreateView(generics.ListCreateAPIView):
    """TODO: List/Create comments on article"""
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        # TODO: Implement comment queryset by article_id
        pass

    def perform_create(self, serializer):
        # TODO: Save comment with article and user
        pass