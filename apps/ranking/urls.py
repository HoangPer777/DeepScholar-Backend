from django.urls import path

from apps.ranking.views import AuthorRankingView


urlpatterns = [
    path("authors/ranking/", AuthorRankingView.as_view(), name="author-ranking"),
]