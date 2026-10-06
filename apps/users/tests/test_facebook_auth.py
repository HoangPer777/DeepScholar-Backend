import time
from unittest.mock import Mock, patch

import requests
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.users.models import User


class FacebookAuthApiTests(TestCase):
    url = "/api/v1/auth/facebook/"
    app_id = "facebook-test-app"
    app_secret = "facebook-test-secret"
    access_token = "facebook-user-token"

    def setUp(self):
        self.client = APIClient()

    @staticmethod
    def response(payload, status_code=200):
        response = Mock()
        response.status_code = status_code
        response.ok = 200 <= status_code < 400
        response.json.return_value = payload
        return response

    def debug_data(self, **overrides):
        data = {
            "is_valid": True,
            "app_id": self.app_id,
            "type": "USER",
            "user_id": "facebook-user-1",
            "expires_at": int(time.time()) + 3600,
            "data_access_expiration_time": int(time.time()) + 3600,
        }
        data.update(overrides)
        return {"data": data}

    def me_data(self, **overrides):
        data = {
            "id": "facebook-user-1",
            "name": "Facebook Test User",
            "email": "facebook-user@example.com",
            "picture": {"data": {"url": "https://example.test/avatar.jpg"}},
        }
        data.update(overrides)
        return data

    def settings_context(self):
        return override_settings(
            FACEBOOK_APP_ID=self.app_id,
            FACEBOOK_APP_SECRET=self.app_secret,
            FACEBOOK_GRAPH_API_VERSION="v-test",
            FACEBOOK_GRAPH_TIMEOUT_SECONDS=3,
        )

    @patch("apps.users.views.requests.get")
    def test_valid_token_must_belong_to_configured_app(self, mock_get):
        mock_get.side_effect = [
            self.response(self.debug_data()),
            self.response(self.me_data()),
        ]

        with self.settings_context():
            response = self.client.post(
                self.url,
                {"access_token": self.access_token},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data["access"])
        self.assertEqual(User.objects.filter(provider="facebook").count(), 1)
        self.assertEqual(mock_get.call_count, 2)
        self.assertEqual(
            mock_get.call_args_list[0].args[0],
            "https://graph.facebook.com/v-test/debug_token",
        )
        self.assertEqual(
            mock_get.call_args_list[0].kwargs["params"],
            {
                "input_token": self.access_token,
                "access_token": f"{self.app_id}|{self.app_secret}",
            },
        )
        self.assertEqual(mock_get.call_args_list[0].kwargs["timeout"], 3)
        self.assertEqual(
            mock_get.call_args_list[1].kwargs["params"]["fields"],
            "id,name,picture",
        )
        response_text = response.content.decode()
        self.assertNotIn(self.access_token, response_text)
        self.assertNotIn(self.app_secret, response_text)

    @patch("apps.users.views.requests.get")
    def test_token_from_another_facebook_app_is_rejected_before_user_lookup(self, mock_get):
        mock_get.return_value = self.response(
            self.debug_data(app_id="another-facebook-app")
        )

        with self.settings_context():
            response = self.client.post(
                self.url,
                {"access_token": self.access_token},
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.data["detail"], "Invalid Facebook token")
        self.assertEqual(mock_get.call_count, 1)
        self.assertFalse(User.objects.filter(provider="facebook").exists())

    @patch("apps.users.views.requests.get")
    def test_valid_token_without_email_uses_stable_fallback(self, mock_get):
        mock_get.side_effect = [
            self.response(self.debug_data()),
            self.response(self.me_data(email=None)),
        ]

        with self.settings_context():
            response = self.client.post(
                self.url,
                {"access_token": self.access_token},
                format="json",
            )

        self.assertEqual(response.status_code, 200)
        user = User.objects.get(provider="facebook")
        self.assertEqual(user.email, "facebook-user-1@facebook.com")

    @patch("apps.users.views.requests.get")
    def test_expired_token_is_rejected_without_creating_user(self, mock_get):
        mock_get.return_value = self.response(
            self.debug_data(expires_at=int(time.time()) - 1)
        )

        with self.settings_context():
            response = self.client.post(
                self.url,
                {"access_token": self.access_token},
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(mock_get.call_count, 1)
        self.assertFalse(User.objects.filter(provider="facebook").exists())

    @patch("apps.users.views.requests.get")
    def test_invalid_debug_token_is_rejected_without_user_lookup(self, mock_get):
        mock_get.return_value = self.response(self.debug_data(is_valid=False))

        with self.settings_context():
            response = self.client.post(
                self.url,
                {"access_token": self.access_token},
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(mock_get.call_count, 1)
        self.assertFalse(User.objects.filter(provider="facebook").exists())

    @patch("apps.users.views.requests.get")
    def test_missing_debug_user_id_is_rejected_without_user_lookup(self, mock_get):
        mock_get.return_value = self.response(self.debug_data(user_id=None))

        with self.settings_context():
            response = self.client.post(
                self.url,
                {"access_token": self.access_token},
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(mock_get.call_count, 1)
        self.assertFalse(User.objects.filter(provider="facebook").exists())

    @patch("apps.users.views.requests.get")
    def test_identity_mismatch_between_debug_and_me_is_rejected(self, mock_get):
        mock_get.side_effect = [
            self.response(self.debug_data()),
            self.response(self.me_data(id="different-facebook-user")),
        ]

        with self.settings_context():
            response = self.client.post(
                self.url,
                {"access_token": self.access_token},
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(User.objects.filter(provider="facebook").exists())

    @patch("apps.users.views.requests.get")
    def test_provider_timeout_fails_closed_without_leaking_token(self, mock_get):
        mock_get.side_effect = requests.Timeout("provider timeout")

        with self.settings_context():
            response = self.client.post(
                self.url,
                {"access_token": self.access_token},
                format="json",
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.data["detail"],
            "Facebook login is temporarily unavailable.",
        )
        response_text = response.content.decode()
        self.assertNotIn(self.access_token, response_text)
        self.assertFalse(User.objects.filter(provider="facebook").exists())

    @patch("apps.users.views.requests.get")
    def test_malformed_provider_response_fails_closed(self, mock_get):
        malformed_response = self.response({})
        malformed_response.json.side_effect = ValueError("not json")
        mock_get.return_value = malformed_response

        with self.settings_context():
            response = self.client.post(
                self.url,
                {"access_token": self.access_token},
                format="json",
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.data["detail"],
            "Facebook login is temporarily unavailable.",
        )
        self.assertFalse(User.objects.filter(provider="facebook").exists())

    @patch("apps.users.views.requests.get")
    def test_missing_server_configuration_fails_closed_before_provider_call(self, mock_get):
        with override_settings(FACEBOOK_APP_ID="", FACEBOOK_APP_SECRET=""):
            response = self.client.post(
                self.url,
                {"access_token": self.access_token},
                format="json",
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.data["detail"], "Facebook login is not configured.")
        mock_get.assert_not_called()
        self.assertFalse(User.objects.filter(provider="facebook").exists())
