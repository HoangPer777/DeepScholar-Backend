from django.urls import path

from apps.interactions.views import BookmarkToggleView, CommentListCreateView, LikeToggleView, BookmarkedArticlesView


urlpatterns = [
    path("articles/<int:pk>/like/", LikeToggleView.as_view(), name="article-like-toggle"),
    path("articles/<int:pk>/bookmark/", BookmarkToggleView.as_view(), name="article-bookmark-toggle"),
    path("articles/<int:pk>/comments/", CommentListCreateView.as_view(), name="article-comments"),
    path("bookmarks/", BookmarkedArticlesView.as_view(), name="bookmarked-articles"),
]