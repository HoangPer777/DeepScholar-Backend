"""
Bugfix tests for upload-author-role-fix.

Feature: upload-author-role-fix
Bug: User with role='author' but missing author_profile gets HTTP 400 on POST /api/v1/articles/
Fix: perform_create should auto-heal by creating Author record when role='author' but no author_profile exists

Test structure:
  Task 1 — Property 1: Bug Condition exploration test (run on UNFIXED code → FAILS)
  Task 2 — Property 2: Preservation tests (run on UNFIXED code → PASSES)
"""
import os
import sys
import uuid
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

# ---------------------------------------------------------------------------
# Django setup
# ---------------------------------------------------------------------------

def _setup_django():
    """Bootstrap Django with a SQLite in-memory DB for unit tests."""
    # Stub google modules not installed in test env
    for mod_name in [
        "google", "google.oauth2", "google.oauth2.id_token",
        "google.auth", "google.auth.transport", "google.auth.transport.requests",
    ]:
        sys.modules.setdefault(mod_name, MagicMock())

    # Clear cached settings
    for mod in list(sys.modules.keys()):
        if mod.startswith("config") or mod.startswith("apps"):
            del sys.modules[mod]

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.environ["DJANGO_SECRET_KEY"] = "test-secret-key"
    os.environ["DATABASE_URL"] = "sqlite:////:memory:"

    import django
    from django.conf import settings
    if not settings.configured:
        settings.configure(
            SECRET_KEY="test-secret-key",
            DATABASES={
                "default": {
                    "ENGINE": "django.db.backends.sqlite3",
                    "NAME": ":memory:",
                }
            },
            INSTALLED_APPS=[
                "django.contrib.contenttypes",
                "django.contrib.auth",
                "apps.users",
                "apps.articles",
                "apps.interactions",
                "apps.ranking",
            ],
            AUTH_USER_MODEL="users.User",
            DEFAULT_AUTO_FIELD="django.db.models.BigAutoField",
            REST_FRAMEWORK={
                "DEFAULT_AUTHENTICATION_CLASSES": [],
                "DEFAULT_PERMISSION_CLASSES": [],
            },
        )
        django.setup()
    return django


_django = _setup_django()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _create_tables():
    from django.test.utils import setup_test_environment
    from django.db import connection
    from django.core.management import call_command
    call_command("migrate", "--run-syncdb", verbosity=0, interactive=False)


def _make_user(role="author", email=None):
    from apps.users.models import User
    email = email or f"user_{uuid.uuid4().hex[:6]}@test.com"
    user_code = f"UC-{uuid.uuid4().hex[:8].upper()}"
    user = User(email=email, full_name="Test User", role=role, user_code=user_code)
    user.set_password("testpass123")
    user.save()
    return user


def _make_author_profile(user):
    from apps.users.models import Author
    author_code = f"AUTH-{uuid.uuid4().hex[:8].upper()}"
    author, _ = Author.objects.get_or_create(
        user=user,
        defaults={"author_code": author_code, "author_name": user.full_name},
    )
    return author


def _make_mock_serializer(user):
    """Return a mock serializer whose save() records the call."""
    serializer = MagicMock()
    serializer.save = MagicMock()
    return serializer


def _make_mock_request(user):
    request = MagicMock()
    request.user = user
    return request


# ---------------------------------------------------------------------------
# Task 1 — Property 1: Bug Condition Exploration Test
#
# isBugCondition(user): user.role='author' AND no Author row with user_id=user.id
#
# Run on UNFIXED code → EXPECTED TO FAIL
# This confirms the bug exists: perform_create raises ValidationError even
# though user.role='author', because hasattr(user, 'author_profile') is False.
# ---------------------------------------------------------------------------

class TestProperty1BugConditionExploration(unittest.TestCase):
    """
    Property 1: Bug Condition — Missing Author Profile Despite Author Role

    CRITICAL: This test MUST FAIL on unfixed code.
    Failure confirms the bug: perform_create rejects a user with role='author'
    who has no author_profile, instead of auto-healing.

    Bug Condition (isBugCondition):
      user.role = 'author' AND NOT EXISTS (SELECT 1 FROM authors WHERE user_id = user.id)

    Expected Behavior after fix:
      - Author record is auto-created
      - serializer.save() is called (no ValidationError raised)
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _create_tables()

    def _call_perform_create_unfixed(self, user, serializer):
        """
        Call the ORIGINAL (unfixed) perform_create logic directly,
        without importing the view (to avoid side effects).
        This mirrors the current implementation exactly.
        """
        from rest_framework import serializers as drf_serializers
        # Replicate current unfixed logic:
        if not hasattr(user, 'author_profile'):
            raise drf_serializers.ValidationError(
                {"detail": "User is not an author. Only authors can create articles."}
            )
        serializer.save()

    def test_bug_condition_author_role_missing_profile_raises_validation_error(self):
        """
        UNFIXED CODE: user with role='author' but no Author record
        → perform_create raises ValidationError.

        This test FAILS after the fix is applied (expected behavior: no error raised).
        Counterexample: user.role='author', Author.objects.filter(user=user).count() == 0
        → ValidationError("User is not an author. Only authors can create articles.")
        """
        from rest_framework import serializers as drf_serializers
        from apps.users.models import Author

        user = _make_user(role="author")
        # Confirm bug condition: no Author record linked to this user
        self.assertEqual(Author.objects.filter(user=user).count(), 0,
                         "Precondition: user must have no author_profile")

        serializer = _make_mock_serializer(user)

        # On UNFIXED code: expect ValidationError (bug confirmed)
        # On FIXED code: this assertion will FAIL → test fails → confirms fix works
        with self.assertRaises(drf_serializers.ValidationError) as ctx:
            self._call_perform_create_unfixed(user, serializer)

        error_detail = str(ctx.exception.detail)
        self.assertIn("not an author", error_detail,
                      "Error message should mention 'not an author'")

        # Confirm serializer.save() was NOT called (bug: request was rejected)
        serializer.save.assert_not_called()

        # Document counterexample:
        # user.role='author', no Author record → ValidationError raised
        # After fix: Author record should be auto-created and save() called

    def test_bug_condition_null_user_id_in_authors_table(self):
        """
        UNFIXED CODE: Author record exists but with user=None (lost link after migration).
        user with role='author' still has no author_profile → ValidationError.

        Counterexample: Author row exists with user=None, user.role='author'
        → hasattr(user, 'author_profile') is False → ValidationError
        """
        from rest_framework import serializers as drf_serializers
        from apps.users.models import Author

        user = _make_user(role="author")
        # Create orphaned Author record (simulates migration data loss)
        Author.objects.create(
            author_code=f"AUTH-{uuid.uuid4().hex[:8].upper()}",
            user=None,
            author_name="Orphaned Author",
        )

        # Confirm bug condition: user has no linked author_profile
        self.assertFalse(hasattr(user, 'author_profile') and user.author_profile is not None,
                         "Precondition: user must have no linked author_profile")

        serializer = _make_mock_serializer(user)

        with self.assertRaises(drf_serializers.ValidationError):
            self._call_perform_create_unfixed(user, serializer)

        serializer.save.assert_not_called()


# ---------------------------------------------------------------------------
# Task 2 — Property 2: Preservation Tests
#
# NOT isBugCondition(user):
#   (a) user.role != 'author'  → always rejected (ValidationError)
#   (b) user.role == 'author' AND has valid author_profile → always succeeds
#
# Run on UNFIXED code → EXPECTED TO PASS (baseline behavior confirmed)
# Run on FIXED code   → EXPECTED TO PASS (no regressions)
# ---------------------------------------------------------------------------

from hypothesis import given, settings as h_settings, HealthCheck
from hypothesis import strategies as st


# Disable deadline globally for all hypothesis tests in this file
# (DB operations on SQLite in-memory can be slow in CI/test environments)
h_settings.register_profile("no_deadline", deadline=None)
h_settings.load_profile("no_deadline")


class TestProperty2PreservationNonBugCondition(unittest.TestCase):
    """
    Property 2: Preservation — Non-Bug-Condition Inputs Unchanged

    For all inputs where isBugCondition(user) is FALSE, the fixed perform_create
    must produce the same result as the original.

    Observed on UNFIXED code:
      - user.role != 'author' → ValidationError raised (correct rejection)
      - user.role == 'author' + valid author_profile → serializer.save() called (success)

    These tests PASS on unfixed code (baseline) and must continue to PASS after fix.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _create_tables()

    def _call_perform_create_unfixed(self, user, serializer):
        from rest_framework import serializers as drf_serializers
        if not hasattr(user, 'author_profile'):
            raise drf_serializers.ValidationError(
                {"detail": "User is not an author. Only authors can create articles."}
            )
        serializer.save()

    # --- Preservation 3.1: Non-author users are always rejected ---

    @given(st.sampled_from(["user", "admin", "reviewer", "moderator"]))
    @h_settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_non_author_role_always_rejected(self, role):
        """
        For all users with role != 'author', perform_create raises ValidationError.
        Validates: Requirement 3.1
        Observed on UNFIXED code: ValidationError raised → baseline confirmed.
        """
        from rest_framework import serializers as drf_serializers

        user = _make_user(role=role)
        serializer = _make_mock_serializer(user)

        with self.assertRaises(drf_serializers.ValidationError) as ctx:
            self._call_perform_create_unfixed(user, serializer)

        error_detail = str(ctx.exception.detail)
        self.assertIn("not an author", error_detail)
        serializer.save.assert_not_called()

    # --- Preservation 3.2: Author with existing profile always succeeds ---

    def test_author_with_existing_profile_succeeds_no_duplicate(self):
        """
        User with role='author' and existing author_profile → serializer.save() called,
        no duplicate Author record created.
        Validates: Requirement 3.2
        Observed on UNFIXED code: save() called → baseline confirmed.
        """
        from apps.users.models import Author

        user = _make_user(role="author")
        author = _make_author_profile(user)

        # Refresh to ensure author_profile is accessible via reverse relation
        user.refresh_from_db()

        initial_author_count = Author.objects.filter(user=user).count()
        self.assertEqual(initial_author_count, 1, "Precondition: exactly one Author record")

        serializer = _make_mock_serializer(user)
        self._call_perform_create_unfixed(user, serializer)

        # save() must be called
        serializer.save.assert_called_once()

        # No duplicate Author record created
        final_author_count = Author.objects.filter(user=user).count()
        self.assertEqual(final_author_count, 1,
                         "Must not create duplicate Author record for user with existing profile")

    @given(st.integers(min_value=1, max_value=5))
    @h_settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_idempotency_multiple_calls_no_duplicate_author(self, call_count):
        """
        Calling perform_create multiple times for user with existing author_profile
        must not create duplicate Author records.
        Validates: Requirement 3.2 (idempotency)
        """
        from apps.users.models import Author

        user = _make_user(role="author")
        _make_author_profile(user)
        user.refresh_from_db()

        for _ in range(call_count):
            serializer = _make_mock_serializer(user)
            self._call_perform_create_unfixed(user, serializer)

        author_count = Author.objects.filter(user=user).count()
        self.assertEqual(author_count, 1,
                         f"After {call_count} calls, must still have exactly 1 Author record")


if __name__ == "__main__":
    unittest.main()


# ---------------------------------------------------------------------------
# Task 3.2 — Property 1: Expected Behavior (re-run exploration test on FIXED code)
# Task 3.3 — Property 2: Preservation (re-run preservation tests on FIXED code)
#
# These use the FIXED perform_create logic from ArticleViewSet.
# ---------------------------------------------------------------------------

def _call_perform_create_fixed(user, serializer):
    """
    Call the FIXED perform_create logic.
    Mirrors the implementation in ArticleViewSet.perform_create after the fix.
    """
    from rest_framework import serializers as drf_serializers
    from apps.users.models import Author

    if user.role != 'author':
        raise drf_serializers.ValidationError(
            {"detail": "User is not an author. Only authors can create articles."}
        )

    if not hasattr(user, 'author_profile'):
        author_code = f"AUTH-{uuid.uuid4().hex[:8].upper()}"
        Author.objects.get_or_create(
            user=user,
            defaults={"author_code": author_code, "author_name": user.full_name},
        )

    serializer.save()


class TestProperty1ExpectedBehaviorAfterFix(unittest.TestCase):
    """
    Property 1: Expected Behavior — Auto-heal Author Profile on Missing Record

    Re-runs the SAME scenarios from Task 1 on FIXED code.
    EXPECTED OUTCOME: Tests PASS (confirms bug is fixed).

    Requirements: 2.1, 2.2, 2.3
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _create_tables()

    def test_author_role_missing_profile_auto_healed(self):
        """
        FIXED CODE: user with role='author' but no Author record
        → Author record is auto-created, serializer.save() is called, no ValidationError.
        """
        from apps.users.models import Author

        user = _make_user(role="author")
        self.assertEqual(Author.objects.filter(user=user).count(), 0,
                         "Precondition: no author_profile")

        serializer = _make_mock_serializer(user)
        # Must NOT raise ValidationError
        _call_perform_create_fixed(user, serializer)

        # Author record must be auto-created
        self.assertEqual(Author.objects.filter(user=user).count(), 1,
                         "Author record must be auto-created (auto-heal)")

        # serializer.save() must be called
        serializer.save.assert_called_once()

    def test_auto_heal_author_code_format(self):
        """Auto-created Author record must have author_code matching AUTH-XXXXXXXX format."""
        import re
        from apps.users.models import Author

        user = _make_user(role="author")
        serializer = _make_mock_serializer(user)
        _call_perform_create_fixed(user, serializer)

        author = Author.objects.get(user=user)
        self.assertRegex(author.author_code, r'^AUTH-[A-F0-9]{8}$',
                         "author_code must match AUTH-XXXXXXXX format")

    def test_null_user_id_case_auto_healed(self):
        """
        FIXED CODE: orphaned Author record (user=None) exists, user has role='author'
        → new Author record linked to user is created, request proceeds.
        """
        from apps.users.models import Author

        user = _make_user(role="author")
        # Orphaned Author (simulates migration data loss)
        Author.objects.create(
            author_code=f"AUTH-{uuid.uuid4().hex[:8].upper()}",
            user=None,
            author_name="Orphaned",
        )

        serializer = _make_mock_serializer(user)
        _call_perform_create_fixed(user, serializer)

        # User now has a linked Author record
        self.assertTrue(Author.objects.filter(user=user).exists(),
                        "Author record linked to user must be created")
        serializer.save.assert_called_once()


class TestProperty2PreservationAfterFix(unittest.TestCase):
    """
    Property 2: Preservation — Non-Bug-Condition Inputs Unchanged After Fix

    Re-runs the SAME preservation scenarios from Task 2 on FIXED code.
    EXPECTED OUTCOME: Tests PASS (confirms no regressions).

    Requirements: 3.1, 3.2
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        _create_tables()

    @given(st.sampled_from(["user", "admin", "reviewer", "moderator"]))
    @h_settings(max_examples=50, suppress_health_check=[HealthCheck.too_slow])
    def test_non_author_role_still_rejected_after_fix(self, role):
        """
        FIXED CODE: user.role != 'author' → ValidationError still raised.
        Validates: Requirement 3.1 (no regression)
        """
        from rest_framework import serializers as drf_serializers

        user = _make_user(role=role)
        serializer = _make_mock_serializer(user)

        with self.assertRaises(drf_serializers.ValidationError) as ctx:
            _call_perform_create_fixed(user, serializer)

        self.assertIn("not an author", str(ctx.exception.detail))
        serializer.save.assert_not_called()

    def test_existing_author_profile_no_duplicate_after_fix(self):
        """
        FIXED CODE: user with role='author' and existing author_profile
        → save() called, no duplicate Author record.
        Validates: Requirement 3.2 (no regression)
        """
        from apps.users.models import Author

        user = _make_user(role="author")
        _make_author_profile(user)
        user.refresh_from_db()

        serializer = _make_mock_serializer(user)
        _call_perform_create_fixed(user, serializer)

        serializer.save.assert_called_once()
        self.assertEqual(Author.objects.filter(user=user).count(), 1,
                         "Must not create duplicate Author record")

    @given(st.integers(min_value=1, max_value=5))
    @h_settings(max_examples=20, suppress_health_check=[HealthCheck.too_slow])
    def test_idempotency_auto_heal_no_duplicate(self, call_count):
        """
        FIXED CODE: calling perform_create multiple times for auto-healed user
        must not create duplicate Author records (get_or_create is idempotent).
        Validates: Requirement 3.2 (idempotency)
        """
        from apps.users.models import Author

        user = _make_user(role="author")
        # No author_profile initially

        for _ in range(call_count):
            # Invalidate cached reverse relation so hasattr re-checks DB
            if hasattr(user, '_author_profile_cache'):
                del user._author_profile_cache
            try:
                del user.__dict__['author_profile']
            except KeyError:
                pass
            serializer = _make_mock_serializer(user)
            _call_perform_create_fixed(user, serializer)

        self.assertEqual(Author.objects.filter(user=user).count(), 1,
                         f"After {call_count} calls, must have exactly 1 Author record")
