from django.test import TestCase

from apps.articles.models import Article, PdfProcessingJob
from apps.articles.pdf_jobs import PdfJobConflict, admit_pdf_job
from apps.users.models import User


class PdfJobAdmissionTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="pdf-job-owner@example.com",
            password="StrongPass123!",
            user_code="USR-PDFJOB",
            full_name="PDF Job Owner",
            role=User.ROLE_AUTHOR,
        )
        self.article = Article.objects.create(
            slug="pdf-job-article",
            title="Pending",
            pdf_url="https://files.example/pdf-job.pdf",
        )

    def test_same_key_reuses_task_and_does_not_advance_generation(self):
        key = "70000000-0000-0000-0000-000000000001"

        first, created_first = admit_pdf_job(self.article.id, self.user, key)
        replay, created_replay = admit_pdf_job(self.article.id, self.user, key)

        self.assertTrue(created_first)
        self.assertFalse(created_replay)
        self.assertEqual(first.task_id, replay.task_id)
        self.assertEqual(PdfProcessingJob.objects.count(), 1)
        self.assertEqual(Article.objects.get(pk=self.article.pk).pdf_generation, 1)

    def test_same_key_with_changed_pdf_input_is_rejected(self):
        key = "70000000-0000-0000-0000-000000000002"
        admit_pdf_job(self.article.id, self.user, key)
        Article.objects.filter(pk=self.article.pk).update(pdf_url="https://files.example/changed.pdf")

        with self.assertRaises(PdfJobConflict):
            admit_pdf_job(self.article.id, self.user, key)

        self.assertEqual(PdfProcessingJob.objects.count(), 1)

    def test_different_key_during_active_job_reuses_active_task(self):
        first, _ = admit_pdf_job(
            self.article.id,
            self.user,
            "70000000-0000-0000-0000-000000000003",
        )
        replay, created = admit_pdf_job(
            self.article.id,
            self.user,
            "70000000-0000-0000-0000-000000000004",
        )

        self.assertFalse(created)
        self.assertEqual(first.task_id, replay.task_id)
        self.assertEqual(Article.objects.get(pk=self.article.pk).pdf_generation, 1)
