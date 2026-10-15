import os
from unittest.mock import Mock, patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.articles.models import Article, ArticleAuthor, PdfProcessingJob
from apps.users.models import Author, User


class PdfPipelineProxyTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.author_user = User.objects.create_user(
            email='pdf-owner@example.com',
            password='StrongPass123!',
            user_code='USR-PDFOWNER',
            full_name='PDF Owner',
            role=User.ROLE_AUTHOR,
        )
        self.author = Author.objects.create(
            user=self.author_user,
            author_code='AUTH-PDFOWNER',
            author_name='PDF Owner',
        )
        self.article = Article.objects.create(
            slug='pdf-owner-paper',
            title='Pending AI Extraction',
            pdf_url='https://files.example/paper.pdf',
        )
        ArticleAuthor.objects.create(article=self.article, author=self.author)
        self.client.force_authenticate(self.author_user)

    @staticmethod
    def _response(payload, status_code=200):
        response = Mock()
        response.ok = 200 <= status_code < 300
        response.status_code = status_code
        response.json.return_value = payload
        response.text = ''
        return response

    def _create_pdf_job(self, key):
        from apps.articles.pdf_jobs import admit_pdf_job

        return admit_pdf_job(self.article.id, self.author_user, key)[0]

    @patch.dict(os.environ, {'INTERNAL_SERVICE_KEY': 'test-internal-key'})
    @patch('apps.articles.ai_proxy.requests.post')
    def test_trigger_returns_task_id_without_waiting_for_pipeline(self, post):
        post.side_effect = lambda _url, json, **_kwargs: self._response({
            'status': 'queued',
            'task_id': json['task_id'],
            'slug': self.article.slug,
            'article_id': self.article.id,
        })

        response = self.client.post('/api/v1/ai/trigger/', {
            'slug': self.article.slug,
            'pdf_url': self.article.pdf_url,
            'article_id': self.article.id,
        }, format='json', HTTP_IDEMPOTENCY_KEY='10000000-0000-0000-0000-000000000001')

        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.data['task_id'], post.call_args.kwargs['json']['task_id'])
        call = post.call_args
        self.assertIn('sync=False', call.args[0])
        self.assertEqual(call.kwargs['headers']['X-Internal-Service-Key'], 'test-internal-key')
        self.assertEqual(call.kwargs['timeout'], 30)
        self.assertEqual(PdfProcessingJob.objects.count(), 1)
        self.assertEqual(self.article.__class__.objects.get(pk=self.article.pk).pdf_generation, 1)

    @patch.dict(os.environ, {'INTERNAL_SERVICE_KEY': 'test-internal-key'})
    @patch('apps.articles.ai_proxy.requests.post')
    def test_duplicate_trigger_reuses_the_same_task_and_generation(self, post):
        post.side_effect = lambda _url, json, **_kwargs: self._response({
            'status': 'queued',
            'task_id': json['task_id'],
            'slug': json['slug'],
            'article_id': json['article_id'],
        })
        headers = {'HTTP_IDEMPOTENCY_KEY': '10000000-0000-0000-0000-000000000002'}
        body = {'slug': self.article.slug, 'pdf_url': self.article.pdf_url, 'article_id': self.article.id}

        first = self.client.post('/api/v1/ai/trigger/', body, format='json', **headers)
        second = self.client.post('/api/v1/ai/trigger/', body, format='json', **headers)

        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 202)
        self.assertEqual(first.data['task_id'], second.data['task_id'])
        self.assertEqual(post.call_args_list[0].kwargs['json']['task_id'], post.call_args_list[1].kwargs['json']['task_id'])
        self.assertEqual(PdfProcessingJob.objects.count(), 1)
        self.assertEqual(Article.objects.get(pk=self.article.pk).pdf_generation, 1)

    @patch.dict(os.environ, {'INTERNAL_SERVICE_KEY': 'test-internal-key'})
    @patch('apps.articles.ai_proxy.requests.post')
    def test_missing_ai_task_id_does_not_write_placeholder(self, post):
        post.return_value = self._response({'status': 'failed'})
        response = self.client.post(
            '/api/v1/ai/trigger/',
            {'slug': self.article.slug, 'pdf_url': self.article.pdf_url, 'article_id': self.article.id},
            format='json',
            HTTP_IDEMPOTENCY_KEY='10000000-0000-0000-0000-000000000003',
        )

        self.assertEqual(response.status_code, 502)
        self.article.refresh_from_db()
        self.assertEqual(self.article.title, 'Pending AI Extraction')
        self.assertIsNone(self.article.abstract)
        self.assertIsNone(self.article.content)

    @patch.dict(os.environ, {'INTERNAL_SERVICE_KEY': 'test-internal-key'})
    def test_callback_is_idempotent_and_rejects_stale_generation(self):
        from apps.articles.pdf_jobs import admit_pdf_job

        job, _ = admit_pdf_job(
            self.article.id,
            self.author_user,
            '10000000-0000-0000-0000-000000000004',
        )
        payload = {
            'event': 'article_saved',
            'task_id': str(job.task_id),
            'generation': job.generation,
            'content_revision': job.content_revision,
            'title': 'Extracted title',
            'abstract': 'Extracted abstract',
            'content': 'Extracted content',
        }
        headers = {'HTTP_X_INTERNAL_SERVICE_KEY': 'test-internal-key'}
        first = self.client.post('/api/v1/ai/pdf/callback/', payload, format='json', **headers)
        replay = self.client.post('/api/v1/ai/pdf/callback/', payload, format='json', **headers)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(Article.objects.get(pk=self.article.pk).title, 'Extracted title')
        self.assertEqual(PdfProcessingJob.objects.get(pk=job.task_id).status, PdfProcessingJob.Status.ARTICLE_SAVED)

        completed = self.client.post(
            '/api/v1/ai/pdf/callback/',
            {
                'event': 'embeddings_saved',
                'task_id': str(job.task_id),
                'generation': job.generation,
                'content_revision': job.content_revision,
            },
            format='json',
            **headers,
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(PdfProcessingJob.objects.get(pk=job.task_id).status, PdfProcessingJob.Status.COMPLETED)

        stale_payload = {**payload, 'title': 'Stale replacement', 'generation': job.generation - 1}
        stale = self.client.post('/api/v1/ai/pdf/callback/', stale_payload, format='json', **headers)
        self.assertEqual(stale.status_code, 409)
        self.assertEqual(Article.objects.get(pk=self.article.pk).title, 'Extracted title')

    @patch.dict(os.environ, {'INTERNAL_SERVICE_KEY': 'test-internal-key'})
    def test_article_edit_invalidates_inflight_pdf_callback(self):
        from apps.articles.pdf_jobs import admit_pdf_job

        job, _ = admit_pdf_job(
            self.article.id,
            self.author_user,
            '10000000-0000-0000-0000-000000000005',
        )
        edit = self.client.patch(
            f'/api/v1/articles/{self.article.slug}/',
            {'title': 'Author edited title'},
            format='json',
        )
        self.assertEqual(edit.status_code, 200)
        self.article.refresh_from_db()
        self.assertEqual(self.article.content_revision, 1)
        self.assertEqual(
            PdfProcessingJob.objects.get(pk=job.task_id).error_code,
            'article_revision_changed',
        )

        stale = self.client.post(
            '/api/v1/ai/pdf/callback/',
            {
                'event': 'article_saved',
                'task_id': str(job.task_id),
                'generation': job.generation,
                'content_revision': job.content_revision,
                'title': 'Old extraction',
                'abstract': 'Old abstract',
                'content': 'Old extracted content',
            },
            format='json',
            HTTP_X_INTERNAL_SERVICE_KEY='test-internal-key',
        )
        self.assertEqual(stale.status_code, 409)
        self.article.refresh_from_db()
        self.assertEqual(self.article.title, 'Author edited title')

    @patch.dict(os.environ, {'INTERNAL_SERVICE_KEY': 'test-internal-key'})
    @patch('apps.articles.ai_proxy.requests.get')
    def test_status_returns_progress_for_article_owner(self, get):
        job = self._create_pdf_job('10000000-0000-0000-0000-000000000006')
        get.return_value = self._response({
            'kind': 'pdf',
            'status': 'running',
            'task_id': str(job.task_id),
            'slug': self.article.slug,
            'article_id': self.article.id,
            'generation': job.generation,
            'content_revision': job.content_revision,
            'article_saved': False,
            'embeddings_saved': False,
            'progress': {
                'phase': 'extracting',
                'message': 'Extracting title, abstract and content…',
                'percent': 35,
            },
        })

        response = self.client.get(f'/api/v1/ai/status/?task_id={job.task_id}')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'running')
        self.assertEqual(response.data['progress']['phase'], 'extracting')
        self.assertEqual(response.data['task_id'], str(job.task_id))
        self.assertEqual(get.call_args.kwargs['headers']['X-Internal-Service-Key'], 'test-internal-key')

    @patch.dict(os.environ, {'INTERNAL_SERVICE_KEY': 'test-internal-key'})
    @patch('apps.articles.ai_proxy.requests.get')
    def test_status_hides_another_authors_article(self, get):
        from apps.articles.pdf_jobs import admit_pdf_job

        other_user = User.objects.create_user(
            email='other-pdf-owner@example.com',
            password='StrongPass123!',
            user_code='USR-PDFOTHER',
            full_name='Other PDF Owner',
            role=User.ROLE_AUTHOR,
        )
        other_author = Author.objects.create(
            user=other_user,
            author_code='AUTH-PDFOTHER',
            author_name='Other PDF Owner',
        )
        other_article = Article.objects.create(
            slug='other-pdf-paper',
            title='Other Pending Paper',
            pdf_url='https://files.example/other.pdf',
        )
        ArticleAuthor.objects.create(article=other_article, author=other_author)
        other_job, _ = admit_pdf_job(
            other_article.id,
            other_user,
            '10000000-0000-0000-0000-000000000007',
        )
        get.return_value = self._response({
            'kind': 'pdf',
            'status': 'running',
            'task_id': str(other_job.task_id),
            'slug': other_article.slug,
            'article_id': other_article.id,
            'generation': other_job.generation,
            'content_revision': other_job.content_revision,
            'progress': {'phase': 'running', 'message': 'Working…', 'percent': 5},
        })

        response = self.client.get(f'/api/v1/ai/status/?task_id={other_job.task_id}')

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.data['detail'], 'PDF task not found or expired')
        get.assert_not_called()

    @patch.dict(os.environ, {'INTERNAL_SERVICE_KEY': 'test-internal-key'})
    @patch('apps.articles.ai_proxy.requests.get')
    def test_terminal_status_comes_from_backend_ledger_without_ai_call(self, get):
        job = self._create_pdf_job('10000000-0000-0000-0000-000000000008')
        PdfProcessingJob.objects.filter(task_id=job.task_id).update(
            status=PdfProcessingJob.Status.COMPLETED,
            article_saved=True,
            embeddings_saved=True,
        )

        response = self.client.get(f'/api/v1/ai/status/?task_id={job.task_id}')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'completed')
        self.assertTrue(response.data['article_saved'])
        self.assertTrue(response.data['embeddings_saved'])
        get.assert_not_called()

    @patch.dict(os.environ, {'INTERNAL_SERVICE_KEY': 'test-internal-key'})
    @patch('apps.articles.ai_proxy.requests.get')
    def test_missing_ai_snapshot_marks_active_job_interrupted_and_fences_worker(self, get):
        job = self._create_pdf_job('10000000-0000-0000-0000-000000000009')
        get.return_value = self._response({'detail': 'not found'}, status_code=404)

        response = self.client.get(f'/api/v1/ai/status/?task_id={job.task_id}')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'failed')
        self.assertEqual(response.data['error_code'], 'pdf_job_interrupted')
        job.refresh_from_db()
        self.article.refresh_from_db()
        self.assertEqual(job.status, PdfProcessingJob.Status.FAILED)
        self.assertLessEqual(self.article.pdf_generation_deadline.timestamp(), __import__('time').time())
