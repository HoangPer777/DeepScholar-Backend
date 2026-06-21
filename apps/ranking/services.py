from collections import defaultdict
from dataclasses import dataclass

from django.db import transaction

from apps.articles.models import Article, ArticleAuthor
from apps.interactions.models import Comment, Like
from apps.users.models import Author


ARTICLE_SCORE = 10
LIKE_SCORE = 3
COMMENTER_SCORE = 5


@dataclass(frozen=True)
class AuthorRankingMetrics:
    article_count: int = 0
    like_count: int = 0
    commenter_count: int = 0

    @property
    def total_score(self) -> int:
        return (
            self.article_count * ARTICLE_SCORE
            + self.like_count * LIKE_SCORE
            + self.commenter_count * COMMENTER_SCORE
        )


def calculate_ranking_metrics(author_ids=None):
    """Calculate ranking metrics in bulk without trusting denormalized counters."""
    active_authors = Author.objects.filter(is_active=True)
    if author_ids is not None:
        active_authors = active_authors.filter(id__in=author_ids)
    selected_ids = set(active_authors.values_list("id", flat=True))
    metrics = {author_id: AuthorRankingMetrics() for author_id in selected_ids}
    if not selected_ids:
        return metrics

    article_authors = list(
        ArticleAuthor.objects.filter(
            author_id__in=selected_ids,
            article__is_active=True,
        ).values_list("article_id", "author_id", "author__user_id")
    )
    article_to_selected_authors = defaultdict(set)
    article_to_all_author_users = defaultdict(set)
    article_ids = set()
    for article_id, author_id, user_id in article_authors:
        article_ids.add(article_id)
        article_to_selected_authors[article_id].add(author_id)
        if user_id:
            article_to_all_author_users[article_id].add(user_id)

    # Include co-authors outside the selected page so their self-interactions are
    # still excluded from every selected co-author's score.
    for article_id, user_id in ArticleAuthor.objects.filter(
        article_id__in=article_ids,
        author__user_id__isnull=False,
    ).values_list("article_id", "author__user_id"):
        article_to_all_author_users[article_id].add(user_id)

    article_counts = defaultdict(int)
    like_counts = defaultdict(int)
    commenter_pairs = defaultdict(set)
    for article_id, author_ids_for_article in article_to_selected_authors.items():
        for author_id in author_ids_for_article:
            article_counts[author_id] += 1

    for article_id, user_id in Like.objects.filter(
        article_id__in=article_ids
    ).values_list("article_id", "user_id"):
        if user_id in article_to_all_author_users[article_id]:
            continue
        for author_id in article_to_selected_authors[article_id]:
            like_counts[author_id] += 1

    for article_id, user_id in Comment.objects.filter(
        article_id__in=article_ids
    ).values_list("article_id", "user_id").distinct():
        if user_id in article_to_all_author_users[article_id]:
            continue
        for author_id in article_to_selected_authors[article_id]:
            commenter_pairs[author_id].add((article_id, user_id))

    return {
        author_id: AuthorRankingMetrics(
            article_count=article_counts[author_id],
            like_count=like_counts[author_id],
            commenter_count=len(commenter_pairs[author_id]),
        )
        for author_id in selected_ids
    }


def get_author_ranking_metrics(author: Author) -> AuthorRankingMetrics:
    return calculate_ranking_metrics([author.pk]).get(
        author.pk, AuthorRankingMetrics()
    )


def recalculate_author_score(author: Author) -> int:
    metrics = get_author_ranking_metrics(author)
    Author.objects.filter(pk=author.pk).update(total_score=metrics.total_score)
    author.total_score = metrics.total_score
    return metrics.total_score


def recalculate_authors(author_ids):
    author_ids = set(author_ids)
    metrics_by_author = calculate_ranking_metrics(author_ids)
    authors = list(Author.objects.filter(pk__in=author_ids))
    for author in authors:
        author.total_score = metrics_by_author.get(
            author.id, AuthorRankingMetrics()
        ).total_score
    with transaction.atomic():
        Author.objects.bulk_update(authors, ["total_score"], batch_size=500)
    return metrics_by_author
