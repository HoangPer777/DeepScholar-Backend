from django.urls import path

from apps.interactions.views import (
    ArticleShareView,
    AuthorFollowToggleView,
    BookmarkToggleView,
    BookmarkedArticlesView,
    CommentListCreateView,
    LikeToggleView,
    NotificationListView,
    NotificationMarkReadView,
)

urlpatterns = [
    # Article interactions
    path("articles/<int:pk>/like/", LikeToggleView.as_view(), name="article-like-toggle"),
    path("articles/<int:pk>/bookmark/", BookmarkToggleView.as_view(), name="article-bookmark-toggle"),
    path("articles/<int:pk>/share/", ArticleShareView.as_view(), name="article-share"),
    path("articles/<int:pk>/comments/", CommentListCreateView.as_view(), name="article-comments"),
    # Author interactions
    path("authors/<int:pk>/follow/", AuthorFollowToggleView.as_view(), name="author-follow-toggle"),
    # Bookmarks list
    path("bookmarks/", BookmarkedArticlesView.as_view(), name="bookmarked-articles"),
    # Notifications
    path("notifications/", NotificationListView.as_view(), name="notification-list"),
    path("notifications/<int:pk>/read/", NotificationMarkReadView.as_view(), name="notification-mark-read"),
]
