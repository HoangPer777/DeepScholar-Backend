from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from apps.articles.models import Article
from apps.articles.serializers import ArticleListSerializer
from apps.interactions.models import Comment, Bookmark, Like, ArticleShare, AuthorFollow
from apps.interactions.serializers import CommentSerializer, NotificationSerializer
from apps.users.models import Author, Notification


class LikeToggleView(APIView):
    """Toggle like on an article. POST creates or removes a like."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        article = get_object_or_404(Article, pk=pk, is_active=True)
        like, created = Like.objects.get_or_create(article=article, user=request.user)
        if created:
            article.refresh_from_db(fields=['like_count'])
            return Response({"liked": True, "like_count": article.like_count}, status=status.HTTP_201_CREATED)
        like.delete()
        article.refresh_from_db(fields=['like_count'])
        return Response({"liked": False, "like_count": article.like_count}, status=status.HTTP_200_OK)


class BookmarkToggleView(APIView):
    """Toggle bookmark on an article."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        article = get_object_or_404(Article, pk=pk, is_active=True)
        bookmark, created = Bookmark.objects.get_or_create(article=article, user=request.user)
        if created:
            article.refresh_from_db(fields=['bookmark_count'])
            return Response({"bookmarked": True, "bookmark_count": article.bookmark_count}, status=status.HTTP_201_CREATED)
        bookmark.delete()
        article.refresh_from_db(fields=['bookmark_count'])
        return Response({"bookmarked": False, "bookmark_count": article.bookmark_count}, status=status.HTTP_200_OK)


class ArticleShareView(APIView):
    """Record a share event for an article. Always creates a new record."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        article = get_object_or_404(Article, pk=pk, is_active=True)
        platform = request.data.get("platform", "")
        ArticleShare.objects.create(article=article, user=request.user, platform=platform)
        article.refresh_from_db(fields=['share_count'])
        return Response({"shared": True, "share_count": article.share_count}, status=status.HTTP_201_CREATED)


class CommentListCreateView(generics.ListCreateAPIView):
    """List top-level comments with nested replies, or create a new comment/reply."""
    serializer_class = CommentSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_queryset(self):
        article_pk = self.kwargs['pk']
        return (
            Comment.objects
            .filter(article_id=article_pk, parent=None)
            .select_related('user__author_profile')
            .prefetch_related('replies__user__author_profile')
            .order_by('-created_at')
        )

    def perform_create(self, serializer):
        article = get_object_or_404(Article, pk=self.kwargs['pk'], is_active=True)
        parent_id = self.request.data.get('parent')
        parent = None
        if parent_id:
            parent = get_object_or_404(Comment, pk=parent_id)
            if parent.article_id != article.pk:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"parent": "Parent comment does not belong to this article."})
        serializer.save(article=article, user=self.request.user, parent=parent)


class AuthorFollowToggleView(APIView):
    """Toggle follow/unfollow an author. Requires the requesting user to have an author profile."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        followed_author = get_object_or_404(Author, pk=pk)
        if not hasattr(request.user, 'author_profile') or request.user.author_profile is None:
            return Response({"detail": "Only authors can follow other authors."}, status=status.HTTP_400_BAD_REQUEST)
        follower_author = request.user.author_profile
        if follower_author == followed_author:
            return Response({"detail": "You cannot follow yourself."}, status=status.HTTP_400_BAD_REQUEST)
        follow, created = AuthorFollow.objects.get_or_create(
            follower_author=follower_author,
            followed_author=followed_author,
        )
        if created:
            followed_author.refresh_from_db(fields=['follower_count'])
            return Response({"following": True, "follower_count": followed_author.follower_count}, status=status.HTTP_201_CREATED)
        follow.delete()
        followed_author.refresh_from_db(fields=['follower_count'])
        return Response({"following": False, "follower_count": followed_author.follower_count}, status=status.HTTP_200_OK)


class NotificationListView(generics.ListAPIView):
    """Return paginated notifications for the authenticated user."""
    serializer_class = NotificationSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user).order_by('-created_at')


class NotificationMarkReadView(APIView):
    """Mark a single notification as read. Returns 404 if it doesn't belong to the user."""
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        notification = get_object_or_404(Notification, pk=pk, recipient=request.user)
        notification.is_read = True
        notification.save(update_fields=['is_read'])
        return Response({"id": notification.pk, "is_read": True}, status=status.HTTP_200_OK)


class BookmarkedArticlesView(generics.ListAPIView):
    """Get all bookmarked articles for the authenticated user."""
    serializer_class = ArticleListSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Article.objects.filter(
            bookmarks__user=self.request.user,
            is_active=True,
        ).distinct().order_by('-bookmarks__created_at')
