from django.test import TestCase
from rest_framework.test import APIClient
from unittest.mock import patch

from apps.articles.models import Article, ArticleAuthor
from apps.users.models import Author, User


class AuthorPublishingPermissionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='reader@example.com',
            password='StrongPass123!',
            user_code='USR-READER01',
            full_name='Reader',
        )
        self.author_user = User.objects.create_user(
            email='author@example.com',
            password='StrongPass123!',
            user_code='USR-AUTHOR01',
            full_name='Author',
            role=User.ROLE_AUTHOR,
        )
        self.author = Author.objects.create(
            user=self.author_user,
            author_code='AUTH-OWNER001',
            author_name='Author',
        )

    def test_regular_user_cannot_create_article_or_request_upload_url(self):
        self.client.force_authenticate(self.user)

        create_response = self.client.post('/api/v1/articles/', {
            'slug': 'blocked-paper',
            'title': 'Blocked',
        }, format='json')
        upload_response = self.client.post('/api/v1/articles/upload_url/', {
            'file_name': 'blocked.pdf',
        }, format='json')

        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(upload_response.status_code, 403)
        self.assertFalse(Article.objects.filter(slug='blocked-paper').exists())

        article = Article.objects.create(slug='existing-paper', title='Existing')
        trigger_response = self.client.post('/api/v1/ai/trigger/', {
            'article_id': article.id,
        }, format='json')
        self.assertEqual(trigger_response.status_code, 403)

    def test_active_author_can_create_article(self):
        self.client.force_authenticate(self.author_user)

        response = self.client.post('/api/v1/articles/', {
            'slug': 'allowed-paper',
            'title': 'Allowed',
            'pdf_url': 'https://files.example/allowed.pdf',
        }, format='json')

        self.assertEqual(response.status_code, 201)
        article = Article.objects.get(slug='allowed-paper')
        self.assertTrue(article.authors.filter(pk=self.author.pk).exists())

    @patch('boto3.client')
    def test_active_author_can_request_upload_url(self, mocked_client):
        mocked_client.return_value.generate_presigned_url.return_value = 'https://upload.example/signed'
        self.client.force_authenticate(self.author_user)

        response = self.client.post('/api/v1/articles/upload_url/', {
            'file_name': 'paper.pdf',
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['presigned_url'], 'https://upload.example/signed')

    def test_inactive_author_cannot_create_article(self):
        self.author.is_active = False
        self.author.save(update_fields=['is_active'])
        self.client.force_authenticate(self.author_user)

        response = self.client.post('/api/v1/articles/', {
            'slug': 'inactive-paper',
            'title': 'Inactive',
        }, format='json')

        self.assertEqual(response.status_code, 403)

    def test_author_cannot_trigger_pipeline_for_another_authors_article(self):
        other_user = User.objects.create_user(
            email='other@example.com',
            password='StrongPass123!',
            user_code='USR-OTHER001',
            full_name='Other Author',
            role=User.ROLE_AUTHOR,
        )
        other_author = Author.objects.create(
            user=other_user,
            author_code='AUTH-OTHER001',
            author_name='Other Author',
        )
        article = Article.objects.create(
            slug='other-paper',
            title='Other Paper',
            pdf_url='https://files.example/other.pdf',
        )
        ArticleAuthor.objects.create(article=article, author=other_author)
        self.client.force_authenticate(self.author_user)

        response = self.client.post('/api/v1/ai/trigger/', {
            'article_id': article.id,
            'slug': article.slug,
            'pdf_url': article.pdf_url,
        }, format='json')

        self.assertEqual(response.status_code, 403)
