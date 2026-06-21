from io import StringIO

from django.core.management import call_command
from django.test import TestCase, TransactionTestCase
from rest_framework.test import APIClient

from apps.articles.models import Article, ArticleAuthor
from apps.interactions.models import Comment, Like
from apps.ranking.services import get_author_ranking_metrics, recalculate_author_score
from apps.users.models import Author, User


class RankingFixtureMixin:
    def make_user(self, code, role="user"):
        return User.objects.create_user(
            email=f"{code}@example.com",
            password="test-password",
            user_code=code,
            full_name=code.title(),
            role=role,
        )

    def make_author(self, code):
        user = self.make_user(code, role="author")
        return Author.objects.create(
            author_code=f"AUTH-{code}", user=user, affiliation="DeepScholar Lab"
        )

    def make_article(self, slug, *authors, active=True):
        article = Article.objects.create(slug=slug, title=slug, is_active=active)
        for order, author in enumerate(authors, start=1):
            ArticleAuthor.objects.create(article=article, author=author, order=order)
        return article


class RankingServiceTests(RankingFixtureMixin, TestCase):
    def test_formula_excludes_self_interactions_and_deduplicates_commenter(self):
        author = self.make_author("alice")
        reader = self.make_user("reader")
        article = self.make_article("paper", author)
        Like.objects.create(article=article, user=author.user)
        Like.objects.create(article=article, user=reader)
        Comment.objects.create(article=article, user=author.user, content="self")
        Comment.objects.create(article=article, user=reader, content="one")
        Comment.objects.create(article=article, user=reader, content="two")

        metrics = get_author_ranking_metrics(author)

        self.assertEqual(metrics.article_count, 1)
        self.assertEqual(metrics.like_count, 1)
        self.assertEqual(metrics.commenter_count, 1)
        self.assertEqual(recalculate_author_score(author), 18)

    def test_each_coauthor_receives_score_and_all_coauthor_activity_is_excluded(self):
        first = self.make_author("first")
        second = self.make_author("second")
        reader = self.make_user("reader2")
        article = self.make_article("joint-paper", first, second)
        Like.objects.create(article=article, user=second.user)
        Comment.objects.create(article=article, user=first.user, content="self")
        Comment.objects.create(article=article, user=reader, content="valid")

        self.assertEqual(get_author_ranking_metrics(first).total_score, 15)
        self.assertEqual(get_author_ranking_metrics(second).total_score, 15)

    def test_inactive_article_and_author_do_not_score(self):
        author = self.make_author("inactive")
        self.make_article("hidden", author, active=False)
        self.assertEqual(get_author_ranking_metrics(author).total_score, 0)
        author.is_active = False
        author.save(update_fields=["is_active"])
        self.assertEqual(get_author_ranking_metrics(author).total_score, 0)


class RankingApiTests(RankingFixtureMixin, TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_anonymous_ranking_schema_search_and_global_rank(self):
        authors = [self.make_author(f"author{i}") for i in range(3)]
        for index, author in enumerate(authors):
            for article_index in range(index + 1):
                self.make_article(f"paper-{index}-{article_index}", author)

        response = self.client.get("/api/v1/authors/ranking/?page_size=1&page=2")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 3)
        self.assertEqual(response.data["results"][0]["rank"], 2)
        self.assertEqual(response.data["results"][0]["total_score"], 20)
        self.assertIn("avatar_url", response.data["results"][0])

        search = self.client.get("/api/v1/authors/ranking/?search=author0")
        self.assertEqual(search.data["count"], 1)

    def test_tie_break_is_stable_and_search_is_kept_in_pagination_links(self):
        first = self.make_author("same-first")
        second = self.make_author("same-second")
        self.make_article("same-first-paper", first)
        self.make_article("same-second-paper", second)

        response = self.client.get(
            "/api/v1/authors/ranking/?search=same&page_size=1"
        )

        self.assertEqual(response.data["results"][0]["id"], first.id)
        self.assertIn("search=same", response.data["next"])
        self.assertIn("page_size=1", response.data["next"])

    def test_command_recalculates_score(self):
        author = self.make_author("command")
        self.make_article("command-paper", author)
        output = StringIO()
        call_command("recalculate_author_rankings", author_id=author.id, stdout=output)
        author.refresh_from_db()
        self.assertEqual(author.total_score, 10)
        self.assertIn("Processed 1 author", output.getvalue())


class RankingSignalTests(RankingFixtureMixin, TransactionTestCase):
    reset_sequences = True

    def test_like_comment_and_soft_delete_recalculate_stored_score(self):
        author = self.make_author("signal-author")
        reader = self.make_user("signal-reader")
        article = self.make_article("signal-paper", author)
        author.refresh_from_db()
        self.assertEqual(author.total_score, 10)

        like = Like.objects.create(article=article, user=reader)
        author.refresh_from_db()
        self.assertEqual(author.total_score, 13)

        Comment.objects.create(article=article, user=reader, content="first")
        Comment.objects.create(article=article, user=reader, content="duplicate")
        author.refresh_from_db()
        self.assertEqual(author.total_score, 18)

        like.delete()
        author.refresh_from_db()
        self.assertEqual(author.total_score, 15)

        article.is_active = False
        article.save(update_fields=["is_active"])
        author.refresh_from_db()
        self.assertEqual(author.total_score, 0)
