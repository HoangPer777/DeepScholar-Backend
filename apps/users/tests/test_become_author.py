from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.users.models import Author, User
from apps.users.serializers import RegisterSerializer, SocialAuthSerializer, UserSerializer
from apps.users.services import become_author


def create_user(email='user@example.com', role=User.ROLE_USER, provider='local'):
    return User.objects.create_user(
        email=email,
        password='StrongPass123!',
        user_code=f"USR-{email[:6]}",
        full_name='Test User',
        role=role,
        provider=provider,
    )


class BecomeAuthorServiceTests(TestCase):
    def test_promotes_user_and_is_idempotent(self):
        user = create_user()

        promoted, author, created = become_author(
            user=user,
            author_name='Academic Name',
            affiliation='Test University',
            bio='Researcher',
        )
        promoted_again, author_again, created_again = become_author(user=user)

        self.assertTrue(created)
        self.assertFalse(created_again)
        self.assertEqual(promoted.role, User.ROLE_AUTHOR)
        self.assertEqual(promoted_again.role, User.ROLE_AUTHOR)
        self.assertEqual(author.pk, author_again.pk)
        self.assertEqual(Author.objects.filter(user=user).count(), 1)
        self.assertEqual(author.affiliation, 'Test University')

    def test_social_auth_never_promotes_existing_user_from_request_data(self):
        user = create_user(provider='local')
        serializer = SocialAuthSerializer(data={
            'email': user.email,
            'full_name': user.full_name,
            'provider_id': 'google-id',
            'role': 'author',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)

        authenticated_user = serializer.save(provider='google')

        authenticated_user.refresh_from_db()
        self.assertEqual(authenticated_user.role, User.ROLE_USER)
        self.assertFalse(Author.objects.filter(user=authenticated_user).exists())

    def test_user_serializer_does_not_update_role(self):
        user = create_user()
        serializer = UserSerializer(user, data={'role': 'author'}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save()
        user.refresh_from_db()
        self.assertEqual(user.role, User.ROLE_USER)

    def test_registration_rejects_unknown_role(self):
        serializer = RegisterSerializer(data={
            'email': 'invalid-role@example.com',
            'password': 'StrongPass123!',
            'full_name': 'Invalid Role',
            'role': 'administrator',
        })
        self.assertFalse(serializer.is_valid())
        self.assertIn('role', serializer.errors)

    def test_social_auth_creates_new_account_as_regular_user(self):
        serializer = SocialAuthSerializer(data={
            'email': 'social-new@example.com',
            'full_name': 'Social User',
            'provider_id': 'new-google-id',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        user = serializer.save(provider='google')
        self.assertEqual(user.role, User.ROLE_USER)
        self.assertFalse(Author.objects.filter(user=user).exists())


class BecomeAuthorApiTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = create_user()

    def test_requires_authentication(self):
        response = self.client.post('/api/v1/auth/become-author/', {
            'accepted_author_terms': True,
        }, format='json')
        self.assertEqual(response.status_code, 401)

    def test_rejects_missing_terms_without_writing(self):
        self.client.force_authenticate(self.user)
        response = self.client.post('/api/v1/auth/become-author/', {
            'accepted_author_terms': False,
        }, format='json')
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, User.ROLE_USER)
        self.assertFalse(Author.objects.filter(user=self.user).exists())

    def test_promotes_google_user_and_returns_fresh_role_claim(self):
        self.user.provider = 'google'
        self.user.provider_id = 'google-sub'
        self.user.save(update_fields=['provider', 'provider_id'])
        self.client.force_authenticate(self.user)

        response = self.client.post('/api/v1/auth/become-author/', {
            'author_name': 'Google Researcher',
            'affiliation': 'Deep Scholar Lab',
            'bio': 'AI researcher',
            'accepted_author_terms': True,
        }, format='json')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.data['created'])
        self.assertEqual(response.data['user']['role'], User.ROLE_AUTHOR)
        self.assertIsNotNone(response.data['user']['author_profile'])
        self.assertEqual(AccessToken(response.data['access'])['role'], User.ROLE_AUTHOR)

        second_response = self.client.post('/api/v1/auth/become-author/', {
            'accepted_author_terms': True,
        }, format='json')
        self.assertEqual(second_response.status_code, 200)
        self.assertFalse(second_response.data['created'])
        self.assertEqual(Author.objects.filter(user=self.user).count(), 1)


class AuthorAuditCommandTests(TestCase):
    def test_fix_repairs_both_inconsistency_directions(self):
        missing_profile = create_user('missing@example.com', role=User.ROLE_AUTHOR)
        wrong_role = create_user('wrong@example.com')
        Author.objects.create(
            user=wrong_role,
            author_code='AUTH-WRONG001',
            author_name='Wrong Role',
        )
        unlinked = Author.objects.create(
            author_code='AUTH-UNLINK01',
            author_name='Unlinked',
        )

        call_command('audit_author_profiles', '--fix')

        missing_profile.refresh_from_db()
        wrong_role.refresh_from_db()
        unlinked.refresh_from_db()
        self.assertTrue(Author.objects.filter(user=missing_profile).exists())
        self.assertEqual(wrong_role.role, User.ROLE_AUTHOR)
        self.assertIsNone(unlinked.user)
