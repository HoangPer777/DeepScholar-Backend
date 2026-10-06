from django.test import SimpleTestCase

from config.settings import validate_production_settings


VALID_SECRET_KEY = "s" * 50


class ProductionSettingsSecurityTests(SimpleTestCase):
    def test_production_rejects_debug_enabled(self):
        with self.assertRaisesMessage(
            RuntimeError,
            "DJANGO_DEBUG must be false in production",
        ):
            validate_production_settings(
                environment="production",
                debug=True,
                secret_key=VALID_SECRET_KEY,
            )

    def test_production_rejects_missing_short_and_placeholder_keys(self):
        invalid_keys = (
            "",
            "s" * 49,
            "change-me",
            "django-insecure-" + ("s" * 50),
            "your-secret-key" + ("s" * 50),
        )

        for invalid_key in invalid_keys:
            with self.subTest(invalid_key_length=len(invalid_key)):
                with self.assertRaisesMessage(
                    RuntimeError,
                    "DJANGO_SECRET_KEY must be a non-placeholder value",
                ):
                    validate_production_settings(
                        environment="production",
                        debug=False,
                        secret_key=invalid_key,
                    )

    def test_production_accepts_debug_disabled_and_valid_key(self):
        self.assertIsNone(
            validate_production_settings(
                environment="production",
                debug=False,
                secret_key=VALID_SECRET_KEY,
            )
        )

    def test_non_production_keeps_existing_debug_and_key_policy(self):
        self.assertIsNone(
            validate_production_settings(
                environment="development",
                debug=True,
                secret_key="change-me",
            )
        )
        self.assertIsNone(
            validate_production_settings(
                environment="test",
                debug=False,
                secret_key="",
            )
        )
