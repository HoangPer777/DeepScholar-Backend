import re
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework.test import APIClient

from apps.ranking.tests.test_ranking import RankingFixtureMixin
from apps.users.models import Author


class RankingDatabasePaginationTests(RankingFixtureMixin, TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_ranking_orders_and_limits_in_database(self):
        authors = [self.make_author(f"paged-{index:02d}") for index in range(8)]
        for index, author in enumerate(authors):
            Author.objects.filter(pk=author.pk).update(
                article_count=index,
                like_count=index % 3,
                commenter_count=index % 2,
                total_score=index * 10,
            )

        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(
                "/api/v1/authors/ranking/?page=2&page_size=2"
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["count"], 8)
        self.assertEqual([item["rank"] for item in response.data["results"]], [3, 4])
        self.assertEqual(response.data["results"][0]["id"], authors[5].id)

        author_page_queries = [
            query["sql"].upper()
            for query in queries
            if 'FROM "AUTHORS"' in query["sql"].upper()
            and "LIMIT 2" in query["sql"].upper()
        ]
        self.assertEqual(len(author_page_queries), 1)
        self.assertRegex(
            author_page_queries[0],
            re.compile(r"ORDER BY .*TOTAL_SCORE.*DESC", re.DOTALL),
        )

    @patch("apps.ranking.services.calculate_ranking_metrics")
    def test_ranking_endpoint_does_not_recalculate_all_authors(self, calculate_metrics):
        author = self.make_author("stored-ranking")
        Author.objects.filter(pk=author.pk).update(
            article_count=2,
            like_count=3,
            commenter_count=1,
            total_score=26,
        )

        response = self.client.get("/api/v1/authors/ranking/?page_size=1")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["results"][0]["article_count"], 2)
        self.assertEqual(response.data["results"][0]["like_count"], 3)
        self.assertEqual(response.data["results"][0]["commenter_count"], 1)
        self.assertEqual(response.data["results"][0]["total_score"], 26)
        calculate_metrics.assert_not_called()

    def test_recalculate_command_processes_authors_in_batches(self):
        authors = [self.make_author(f"batch-{index:02d}") for index in range(5)]
        for index, author in enumerate(authors):
            self.make_article(f"batch-paper-{index}", author)

        output = StringIO()
        call_command(
            "recalculate_author_rankings",
            batch_size=2,
            stdout=output,
        )

        self.assertIn("Processed 5 author", output.getvalue())
        for author in authors:
            author.refresh_from_db()
            self.assertEqual(author.article_count, 1)
            self.assertEqual(author.total_score, 10)
