from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient

from apps.articles.views import MAX_PDF_SIZE_BYTES
from apps.users.models import Author, User


class PdfUploadLimitTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = User.objects.create_user(
            email='upload-limit@example.com',
            password='StrongPass123!',
            user_code='USR-UPLOADLIMIT',
            full_name='Upload Limit Author',
            role=User.ROLE_AUTHOR,
        )
        Author.objects.create(
            user=self.user,
            author_code='AUTH-UPLOADLIMIT',
            author_name='Upload Limit Author',
        )
        self.client.force_authenticate(self.user)

    def _request_upload_url(self, file_size):
        return self.client.post(
            '/api/v1/articles/upload_url/',
            {'file_name': 'paper.pdf', 'file_size': file_size},
            format='json',
        )

    def test_missing_zero_negative_and_non_numeric_sizes_are_rejected(self):
        for value in (None, 0, -1, 'not-a-number'):
            with self.subTest(value=value):
                payload = {'file_name': 'paper.pdf'}
                if value is not None:
                    payload['file_size'] = value
                response = self.client.post(
                    '/api/v1/articles/upload_url/', payload, format='json'
                )
                self.assertEqual(response.status_code, 400)

    @patch('boto3.client')
    def test_size_above_25_mib_is_rejected_before_presign(self, mocked_client):
        response = self._request_upload_url(MAX_PDF_SIZE_BYTES + 1)

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.data['max_file_size_bytes'], MAX_PDF_SIZE_BYTES)
        mocked_client.assert_not_called()

    @patch('boto3.client')
    def test_exact_limit_is_signed_into_presigned_put(self, mocked_client):
        mocked_client.return_value.generate_presigned_url.return_value = 'https://upload.example/signed'

        response = self._request_upload_url(MAX_PDF_SIZE_BYTES)

        self.assertEqual(response.status_code, 200)
        params = mocked_client.return_value.generate_presigned_url.call_args.kwargs['Params']
        self.assertEqual(params['ContentLength'], MAX_PDF_SIZE_BYTES)
        self.assertEqual(response.data['max_file_size_bytes'], MAX_PDF_SIZE_BYTES)
